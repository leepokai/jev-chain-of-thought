"""Automatic prompt optimization on Jev: GEPA (Agrawal et al. 2025) and MIPROv2 (Opsahl-Ong et al. 2024) rewrite the instructions of a
one-call Jev program; the proposal / reflection LM is Claude through Vercel AI Gateway's OpenAI-compatible endpoint.
usage: python benchmarks/optimize.py [legalbench:diversity_5 legalbench:hearsay bbh:causal_judgement ...]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dspy

from benchmarks import bbh as bbh_bench
from benchmarks import legalbench as lb
from benchmarks.common import Meter, PRICE, configure, evaluate, exact, feedback_metric, log, table, write
from benchmarks.data import legalbench
from dspy_jev import Predict

DEFAULT = ["legalbench:diversity_5", "legalbench:diversity_6", "legalbench:hearsay", "bbh:causal_judgement", "bbh:disambiguation_qa"]
OUT = Path(__file__).resolve().parent.parent / "results" / "optimized"


def reflection_lm():
    key = os.environ.get("AI_GATEWAY_API_KEY") or os.environ.get("VERCEL_OIDC_TOKEN")
    return dspy.LM(os.environ.get("REFLECTION_MODEL", "openai/anthropic/claude-sonnet-4.5"), api_base="https://ai-gateway.vercel.sh/v1", api_key=key, temperature=1.0, max_tokens=8000)


def load(spec):
    bench, task = spec.split(":")
    if bench == "legalbench":
        sig = lb.FAMILY[task.rstrip("_123456")][0]
        train, val, test = lb.split(legalbench(task))
        return sig, train, val, test
    sig, train, test, _ = bbh_bench.prepare(task)
    return sig, train[:35], train[35:], test


def main(specs):
    lm = configure()
    rlm = reflection_lm()
    OUT.mkdir(parents=True, exist_ok=True)
    rows, out = [], {}
    for spec in specs:
        sig, train, val, test = load(spec)
        base = Predict(sig)
        row = {"task": spec, "train / val / test": f"{len(train)} / {len(val)} / {len(test)}", "direct": f"{evaluate(base, test, exact('answer')):.1f}"}
        for name, make in (("GEPA", lambda: dspy.GEPA(metric=feedback_metric("answer"), auto="light", reflection_lm=rlm, num_threads=16, track_stats=False)),
                           ("MIPROv2", lambda: dspy.MIPROv2(metric=exact("answer"), prompt_model=rlm, task_model=lm, auto="light", num_threads=16, max_bootstrapped_demos=0, max_labeled_demos=4, verbose=False))):
            m = Meter(lm)
            try:
                opt = make().compile(Predict(sig), trainset=train, valset=val, **({"requires_permission_to_run": False} if name == "MIPROv2" else {}))
                score = evaluate(opt, test, exact("answer"))
                opt.save(OUT / f"{spec.replace(':', '-')}.{name.lower()}.json")
                instr = opt.signature.instructions if hasattr(opt, "signature") else next(p.signature.instructions for _, p in opt.named_predictors())
                out[f"{spec}/{name}"] = {"acc": score, "instructions": instr, "jev_calls": m.read()[0], "jev_cost": m.read()[1] * PRICE}
                row[name] = f"{score:.1f}"
                log(f"{spec} {name}: {score:.1f}% on test (Jev calls during optimization: {m.read()[0]})")
            except Exception as e:  # noqa: BLE001 - report and continue with the next optimizer
                row[name] = f"failed: {type(e).__name__}"
                log(f"{spec} {name} failed: {e}")
        rows.append(row)
    md = f"# Automatic prompt optimization (reflection LM {rlm.model}; task LM {lm.model} via {lm._resolve()['kind']})\n\n{table(rows)}\n"
    for k, v in out.items():
        md += f"\n<details><summary>{k}: optimized instructions ({v['acc']:.1f}%)</summary>\n\n```\n{v['instructions']}\n```\n</details>\n"
    write("optimize.md", md)
    (OUT / "summary.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT)
