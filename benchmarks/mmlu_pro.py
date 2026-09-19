"""MMLU-Pro (TIGER-Lab) on Jev under DSPy: every prompting technique on a seeded, category-stratified sample.
train = first 200 of the sample (demo pool), test = the next 500; the validation split's CoT examples are the few-shot demos.
usage: python benchmarks/mmlu_pro.py [--sample 700]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dspy

from benchmarks.common import Meter, PRICE, configure, exact, log, table, techniques, write
from benchmarks.data import LETTERS, mmlu_pro
from benchmarks.mcq import mcq_signature, with_options


def main(sample=700, train_n=200):
    lm = configure()
    items, val = mmlu_pro(sample)
    mk = lambda e, **extra: dspy.Example(question=with_options(e.question, e.options), answer=e.answer, category=e.category, **extra).with_inputs("question")
    items = [mk(e) for e in items]
    exemplars = [mk(e, worked_solution=e.worked_solution) for e in val]
    train_n = min(train_n, len(items) // 3)
    train, test = items[:train_n], items[train_n:]
    sig = mcq_signature(list(LETTERS), "Answer the multiple-choice question.")
    zoo = techniques(sig, train, text_field="question", k=5, many=50, exemplars=exemplars, s2a=False)
    rows, out = [], {}
    for name, prog in zoo.items():
        m = Meter(lm)
        res = dspy.Evaluate(devset=test, metric=exact("answer"), num_threads=16, display_progress=False, failure_score=0.0)(prog)
        calls, tokens = m.read()
        out[name] = {"acc": res.score, "calls_per_q": calls / len(test), "cost": tokens * PRICE}
        rows.append({"technique": name, "accuracy": f"{res.score:.1f}", "calls / q": f"{calls / len(test):.2f}", "cost": f"${tokens * PRICE:.3f}"})
        log(f"mmlu-pro {name}: {res.score:.1f}%  ({calls / len(test):.1f} calls/q, ${tokens * PRICE:.3f})")
    write("mmlu-pro.md", f"# MMLU-Pro ({len(test)} test questions of a {sample}-question stratified sample; model {lm.model} via {lm._resolve()['kind']})\n\n{table(rows)}\n")
    (Path(__file__).resolve().parent.parent / "results" / "mmlu-pro.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else 700)
