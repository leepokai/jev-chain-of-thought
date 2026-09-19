"""BIG-Bench Hard (Suzgun et al. 2022), the 23 option-answer tasks, on Jev under DSPy: every prompting technique.
Per task: train = first 50 items (demo pool for many-shot / kNN), test = next 100; the official 3 exemplars from the repo's prompt files
are the few-shot / few-shot-CoT demos.   usage: python benchmarks/bbh.py [task ...] [--test N]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dspy

from benchmarks.common import Meter, PRICE, configure, exact, log, table, techniques, write
from benchmarks.data import BBH_TASKS, bbh
from benchmarks.mcq import mcq_signature, with_options

TRAIN, TEST = 50, 100


def prepare(task):
    examples, official = bbh(task)
    letters = sorted({l for e in examples for l in e.options}, key=lambda l: (len(l), l))
    sig = mcq_signature(letters, official["description"])
    items = [dspy.Example(question=with_options(e.question, e.options), answer=e.answer).with_inputs("question") for e in examples]
    exemplars = [dspy.Example(question=x["question"], answer=x["answer"], worked_solution=x["worked_solution"]).with_inputs("question") for x in official["exemplars"] if x["answer"] in letters]
    return sig, items[:TRAIN], items[TRAIN:TRAIN + TEST], exemplars


def main(tasks, test_n=TEST):
    global TEST
    TEST = test_n
    lm = configure()
    out, rows = {}, []
    for task in tasks:
        sig, train, test, exemplars = prepare(task)
        zoo = techniques(sig, train, text_field="question", k=3, many=50, exemplars=exemplars, permute=len(sig.output_fields["answer"].annotation.__args__) > 2 if hasattr(sig.output_fields["answer"].annotation, "__args__") else True)
        row, out[task] = {"task": task, "n": len(test)}, {}
        for name, prog in zoo.items():
            m = Meter(lm)
            score = dspy.Evaluate(devset=test, metric=exact("answer"), num_threads=16, display_progress=False, failure_score=0.0)(prog).score
            calls, tokens = m.read()
            out[task][name] = {"acc": score, "calls_per_item": calls / len(test), "cost": tokens * PRICE}
            row[name] = f"{score:.1f}"
            log(f"{task} {name}: {score:.1f}%  ({calls / len(test):.1f} calls/item, ${tokens * PRICE:.3f})")
        rows.append(row)
    names = [k for k in rows[0] if k not in ("task", "n")]
    rows.append({"task": "**mean over tasks**", "n": "", **{n: f"{sum(out[t][n]['acc'] for t in tasks if n in out[t]) / max(1, sum(n in out[t] for t in tasks)):.1f}" for n in names}})
    rows.append({"task": "calls / item", "n": "", **{n: f"{sum(out[t][n]['calls_per_item'] for t in tasks if n in out[t]) / max(1, sum(n in out[t] for t in tasks)):.2f}" for n in names}})
    rows.append({"task": "cost, all tasks", "n": "", **{n: f"${sum(out[t][n]['cost'] for t in tasks if n in out[t]):.2f}" for n in names}})
    write("bbh.md", f"# BIG-Bench Hard ({len(tasks)} tasks, {TEST} test items each; model {lm.model} via {lm._resolve()['kind']})\n\n{table(rows)}\n")
    (Path(__file__).resolve().parent.parent / "results" / "bbh.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(sys.argv[sys.argv.index("--test") + 1]) if "--test" in sys.argv else TEST
    main(args or BBH_TASKS, n)
