"""TypeSafe's CLERC re-ranking cookbook (docs.typesafe.ai/cookbooks/rerank_typesafe) rebuilt on DSPy: the same 40 queries and 30 BM25
candidates (plus the other 110 pooled rows), three formulations: fanout (one call, one noul per candidate), listwise (one choice over the ids),
cot (fanout, then listwise over the top 10 with the fanout scores as established facts).   usage: python benchmarks/clerc.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dspy

from benchmarks.common import Meter, PRICE, configure, log, table, write
from benchmarks.data import clerc
from dspy_jev import Criteria, Predict, render
from dspy_jev.modules import FACTS_FIELD, FACTS_NOTE

INSTRUCTIONS = ("The query excerpt comes from a US federal court opinion and was written immediately around a citation to a precedent; the citation itself "
                "has been removed. Could the candidate passage be from that cited precedent — does it establish the specific legal proposition the query excerpt invokes at its citation point?")
CRIT = Criteria(true="The candidate passage states or establishes the specific rule, standard, holding, or fact pattern that the query excerpt attributes to its removed citation.",
                false="The candidate passage is merely on a similar topic or doctrine; it does not supply the specific proposition the query excerpt relies on.")


def fanout_sig(cands: dict[str, str]):
    fields = {"query_excerpt": dspy.InputField()}
    fields.update({f"c_{c}": dspy.OutputField(desc={"question": INSTRUCTIONS, "candidate_passage": t}) for c, t in cands.items()})
    sig = dspy.Signature(fields, "Judge each candidate passage against the query excerpt.")
    for c in cands:
        sig = sig.with_updated_fields(f"c_{c}", type_=Annotated[bool, CRIT])
    return sig


def listwise_sig(ids: list[str], with_facts: bool):
    fields = {"query_excerpt": dspy.InputField(), "candidates": dspy.InputField()}
    if with_facts:
        fields[FACTS_FIELD] = dspy.InputField(desc=FACTS_NOTE)
    fields["best"] = dspy.OutputField(desc={"question": INSTRUCTIONS, "pick": "The id of the single best candidate."})
    sig = dspy.Signature(fields, "Pick the one candidate passage that is the cited precedent.")
    return sig.with_updated_fields("best", type_=Annotated[Literal[tuple(ids)], Criteria(**{c: f"candidate {c}" for c in ids})])


def rerank(strategy, query, cands, top_k=10):
    ids = list(cands)
    if strategy in ("fanout", "cot"):
        p = Predict(fanout_sig(cands))(query_excerpt=query)
        scores = {c: p.jev[f"c_{c}"]["p"] for c in ids}
        ranking = sorted(ids, key=lambda c: -scores[c])
        if strategy == "fanout":
            return ranking
        head = ranking[:top_k]
        facts = render({f"{c}_relevant": {"p": scores[c]} for c in head})
        q = Predict(listwise_sig(head, True))(query_excerpt=query, candidates={c: cands[c] for c in head}, **{FACTS_FIELD: facts})
        probs = q.jev["best"]["probabilities"]
        return sorted(head, key=lambda c: -probs[c]) + ranking[top_k:]
    q = Predict(listwise_sig(ids, False))(query_excerpt=query, candidates=cands)
    probs = q.jev["best"]["probabilities"]
    return sorted(ids, key=lambda c: -probs[c])


def main():
    lm = configure()
    queries, corpus = clerc()
    if os.environ.get("N"):  # smoke: first N queries only
        queries = queries[: int(os.environ["N"])]
    rows, out = [], {}
    for subset_name, subset in (("cookbook 40", [q for q in queries if q.get("cookbook")]), ("all 150", queries)):
        ranks = {"BM25": [q["candidates"].index(q["gold"]) + 1 for q in subset]}
        for strategy in ("fanout", "listwise", "cot"):
            m = Meter(lm)
            rk = dspy.Parallel(num_threads=8)([(rerank, {"strategy": strategy, "query": q["query"], "cands": {c: corpus[c] for c in q["candidates"]}}) for q in subset])
            ranks[strategy] = [r.index(q["gold"]) + 1 for r, q in zip(rk, subset)]
            calls, tokens = m.read()
            out[f"{subset_name}/{strategy}"] = {"calls": calls, "cost": tokens * PRICE}
            log(f"clerc {subset_name} {strategy}: top-1 {sum(r == 1 for r in ranks[strategy]) / len(subset):.1%}  ({calls} calls, ${tokens * PRICE:.3f})")
        for name, rs in ranks.items():
            at = lambda n: f"{100 * sum(r <= n for r in rs) / len(rs):.1f}"
            rows.append({"subset": subset_name, "method": name, "top-1": at(1), "top-5": at(5), "top-10": at(10), "MRR": f"{sum(1 / r for r in rs) / len(rs):.3f}",
                         "calls / query": "0" if name == "BM25" else f"{out[f'{subset_name}/{name}']['calls'] / len(subset):.1f}", "cost": "$0" if name == "BM25" else f"${out[f'{subset_name}/{name}']['cost']:.3f}"})
            out[f"{subset_name}/{name}"] = {**out.get(f"{subset_name}/{name}", {}), "ranks": rs}
    md = (f"# CLERC re-ranking (TypeSafe cookbook slice; model {lm.model} via {lm._resolve()['kind']})\n\nCookbook, jev-1.12, one noul per pair (30 calls/query): top-1 18% · top-5 35% · top-10 62%.\n\n{table(rows)}\n")
    write("clerc.md", md)
    (Path(__file__).resolve().parent.parent / "results" / "clerc.json").write_text(json.dumps(out))


if __name__ == "__main__":
    main()
