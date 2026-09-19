"""LegalBench rule-application tasks (Guha et al. 2023) on Jev under DSPy: every prompting technique, plus `chain` (ask the statute's
sub-conditions, then the conclusion with them as facts) and `code` (ask the sub-conditions, apply the statute in Python).
Splits per task: train = demo pool / optimizer train, val = optimizer validation, test = reported.
usage: python benchmarks/legalbench.py [task ...]      results → results/legalbench.md + results/legalbench.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dspy

from benchmarks.common import Meter, PRICE, configure, evaluate, exact, log, table, techniques, write
from benchmarks.data import LEGALBENCH_TASKS, legalbench
from dspy_jev import Chain, Predict


class Diversity(dspy.Signature):
    """A federal court has diversity jurisdiction over a claim when (1) the parties are completely diverse: no plaintiff is a citizen of the same state as any defendant, and (2) the amount in controversy exceeds $75,000. A single plaintiff may aggregate all of their claims against a single defendant to reach the threshold; claims by different plaintiffs, or against different defendants, are not aggregated."""
    facts: str = dspy.InputField()
    answer: bool = dspy.OutputField(desc="Is there diversity jurisdiction over this case?")


DiversityFacts = dspy.Signature({"facts": dspy.InputField(),
                                 "parties_are_diverse": dspy.OutputField(desc="Are the parties completely diverse: does no plaintiff share a state of citizenship with any defendant?"),
                                 "aic_is_met": dspy.OutputField(desc="Is the amount-in-controversy requirement met: does some plaintiff's total claims against some defendant exceed $75,000? Aggregate only one plaintiff's claims against one defendant; exactly $75,000 does not exceed $75,000.")},
                                Diversity.instructions).with_updated_fields("parties_are_diverse", type_=bool).with_updated_fields("aic_is_met", type_=bool)


class Hearsay(dspy.Signature):
    """Hearsay is (1) an out-of-court statement, made by a person, (2) offered in court to prove the truth of the matter asserted in the statement. Non-assertive conduct, statements not offered for their truth (e.g. to show effect on the listener, or that words were spoken), and statements made in the present court proceeding are not hearsay."""
    facts: str = dspy.InputField()
    answer: bool = dspy.OutputField(desc="Is this evidence hearsay?")


HearsayFacts = dspy.Signature({"facts": dspy.InputField(),
                               "out_of_court_statement": dspy.OutputField(desc="Is the evidence a statement (an assertion, oral, written or by assertive conduct) that was made outside the current court proceeding?"),
                               "offered_for_truth": dspy.OutputField(desc="Is the statement being offered to prove that what it asserts is true, rather than for some other purpose (effect on the listener, that the words were said, state of mind)?")},
                              Hearsay.instructions).with_updated_fields("out_of_court_statement", type_=bool).with_updated_fields("offered_for_truth", type_=bool)


class PersonalJurisdiction(dspy.Signature):
    """A court in a forum state has personal jurisdiction over a defendant when (1) the defendant is domiciled in the forum state (general jurisdiction), or (2) the defendant has sufficient minimum contacts with the forum state AND the plaintiff's claim arises out of or relates to those contacts (specific jurisdiction)."""
    facts: str = dspy.InputField()
    answer: bool = dspy.OutputField(desc="Does the court have personal jurisdiction over the defendant?")


PJFacts = dspy.Signature({"facts": dspy.InputField(),
                          "domiciled_in_forum": dspy.OutputField(desc="Is the defendant domiciled in (lives in) the state where the suit is brought?"),
                          "has_contacts": dspy.OutputField(desc="Does the defendant have purposeful minimum contacts with the forum state, such as doing business, travelling there for work, or directing conduct at it?"),
                          "claim_arises_from_contacts": dspy.OutputField(desc="Does the plaintiff's claim arise out of or relate to the defendant's contacts with the forum state?")},
                         PersonalJurisdiction.instructions)
for _f in ("domiciled_in_forum", "has_contacts", "claim_arises_from_contacts"):
    PJFacts = PJFacts.with_updated_fields(_f, type_=bool)

FAMILY = {
    "diversity": (Diversity, DiversityFacts, lambda p: p.parties_are_diverse and p.aic_is_met),
    "hearsay": (Hearsay, HearsayFacts, lambda p: p.out_of_court_statement and p.offered_for_truth),
    "personal_jurisdiction": (PersonalJurisdiction, PJFacts, lambda p: p.domiciled_in_forum or (p.has_contacts and p.claim_arises_from_contacts)),
}


class Code(dspy.Module):
    """Program-aided: Jev answers the sub-conditions, Python applies the statute."""

    def __init__(self, facts_sig, rule):
        self.facts = Predict(facts_sig)
        self.rule = rule

    def forward(self, **kwargs):
        p = self.facts(**kwargs)
        p["answer"] = bool(self.rule(p))
        return p


def split(examples):
    n = len(examples)
    tr, va = (100, 50) if n >= 300 else (30, 14) if n >= 90 else (15, 5)
    return examples[:tr], examples[tr:tr + va], examples[tr + va:]


def main(tasks):
    lm = configure()
    out, rows, subs = {}, [], []
    for task in tasks:
        sig, facts_sig, rule = FAMILY[task.rstrip("_123456")]
        train, val, test = split(legalbench(task))
        zoo = techniques(sig, train, text_field="facts", k=5, many=min(50, len(train)))
        zoo["chain"] = Chain(facts_sig, sig)
        zoo["code"] = Code(facts_sig, rule)
        row, out[task] = {"task": task, "n": len(test)}, {}
        for name, prog in zoo.items():
            m = Meter(lm)
            res = dspy.Evaluate(devset=test, metric=exact("answer"), num_threads=16, display_progress=False, failure_score=0.0)(prog)
            calls, tokens = m.read()
            out[task][name] = {"acc": res.score, "calls_per_row": calls / len(test), "cost": tokens * PRICE}
            row[name] = f"{res.score:.1f}"
            log(f"{task} {name}: {res.score:.1f}%  ({calls / len(test):.1f} calls/row, ${tokens * PRICE:.3f})")
            if name in ("chain", "code") and "parties_are_diverse" in test[0]:
                sub = {k: sum(p[k] == ex[k] for ex, p, _ in res.results) / len(test) * 100 for k in ("parties_are_diverse", "aic_is_met")}
                subs.append({"task": task, "strategy": name, **{k: f"{v:.1f}" for k, v in sub.items()}})
                out[task][name]["sub"] = sub
        rows.append(row)
    names = [k for k in rows[0] if k not in ("task", "n")]
    rows.append({"task": "calls / row", "n": "", **{n: f"{sum(out[t][n]['calls_per_row'] for t in tasks) / len(tasks):.2f}" for n in names}})
    rows.append({"task": "cost, all tasks", "n": "", **{n: f"${sum(out[t][n]['cost'] for t in tasks):.2f}" for n in names}})
    md = f"# LegalBench rule-application tasks (test splits; model {lm.model} via {lm._resolve()['kind']})\n\n{table(rows)}\n"
    if subs:
        md += f"\nSub-condition accuracy on the diversity tasks (gold shipped with the dataset):\n\n{table(subs)}\n"
    write("legalbench.md", md)
    (Path(__file__).resolve().parent.parent / "results" / "legalbench.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:] or LEGALBENCH_TASKS)
