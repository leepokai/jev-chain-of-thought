"""Synthetic rubric memos (100 OCR-noised transaction memos, three questions that depend on each other) on Jev under DSPy:
direct, self-refine, chain (rubric inputs first), chain + refine.   usage: python benchmarks/synthetic.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dspy

from benchmarks.common import Meter, PRICE, configure, log, table, write
from benchmarks.data import memos
from dspy_jev import Chain, Criteria, Predict, SelfRefine

RULES = ("Risk score = amount points + origin points + note points. Amount: >= 50,000 -> 2; 10,000-49,999 -> 1; < 10,000 -> 0. "
         "Origin in {Cayman Islands, Panama, Iran, Belize} -> +2, else 0. Notes: sanctions screening / fraud pattern / structuring or laundering -> +3; "
         "dispute, chargeback, first-time counterparty -> +1; routine invoice -> 0; verified recurring vendor, verified payroll, internal transfer between own accounts -> -1. "
         "The text is OCR output and may contain character substitutions (O/0, l/1, S/5, dropped spaces).")


class Memo(dspy.Signature):
    __doc__ = RULES
    memo: str = dspy.InputField()
    risk_level: Annotated[Literal["HIGH", "MEDIUM", "LOW", "NONE"], Criteria(HIGH="score >= 4", MEDIUM="score 2-3", LOW="score 1", NONE="score <= 0")] = dspy.OutputField(desc="Risk level of this transaction.")
    requires_review: Annotated[bool, Criteria(true="Risk is HIGH or MEDIUM, or the notes mention a dispute.", false="Risk is LOW or NONE and the notes do not mention a dispute.")] = dspy.OutputField(desc="Does this need manual review? True when risk level is HIGH or MEDIUM, or the notes mention a dispute.")
    action_tier: Annotated[Literal["TIER_1", "TIER_2", "TIER_3"], Criteria(TIER_1="risk HIGH or amount >= 50,000", TIER_2="otherwise, risk MEDIUM or amount >= 10,000", TIER_3="everything else")] = dspy.OutputField(desc="Action tier for this transaction.")


class Facts(dspy.Signature):
    """Read the rubric's three inputs off the memo. The text is OCR output (O/0, l/1, S/5 substitutions, dropped spaces)."""
    memo: str = dspy.InputField()
    amount_bucket: Annotated[Literal["large", "mid", "small"], Criteria(large=">= 50,000", mid="10,000 to 49,999", small="< 10,000")] = dspy.OutputField(desc="Which bracket is the USD Amount in?")
    origin_high_risk: bool = dspy.OutputField(desc="Is the Origin country one of: Cayman Islands, Panama, Iran, Belize?")
    note_kind: Annotated[Literal["severe", "minor", "routine", "trusted"], Criteria(severe="sanctions screening, fraud pattern, structuring or laundering", minor="dispute, chargeback, or first-time counterparty", routine="routine invoice settlement", trusted="verified recurring vendor, verified payroll, or internal transfer between own accounts")] = dspy.OutputField(desc="Which category do the Notes fall in?")


FIELDS = ["risk_level", "requires_review", "action_tier"]


def all3(example, pred, trace=None, pred_name=None, pred_trace=None):
    return float(all(pred[f] == example[f] for f in FIELDS))


def main():
    lm = configure()
    data = memos()
    zoo = {"direct": Predict(Memo), "refine": SelfRefine(Memo, rounds=3), "chain": Chain(Facts, Memo), "chain+refine": Chain(Facts, Memo, refine=3)}
    rows, out = [], {}
    for name, prog in zoo.items():
        m = Meter(lm)
        res = dspy.Evaluate(devset=data, metric=all3, num_threads=16, display_progress=False, failure_score=0.0)(prog)
        calls, tokens = m.read()
        per = {f: 100 * sum(p[f] == ex[f] for ex, p, _ in res.results) / len(data) for f in FIELDS}
        out[name] = {"all3": res.score, **per, "calls_per_doc": calls / len(data), "cost": tokens * PRICE}
        rows.append({"strategy": name, **{f: f"{v:.0f}" for f, v in per.items()}, "all 3": f"{res.score:.0f}", "calls / doc": f"{calls / len(data):.2f}", "cost": f"${tokens * PRICE:.4f}"})
        log(f"synthetic {name}: all-3 {res.score:.0f}%")
    write("synthetic.md", f"# Synthetic rubric memos (100 docs; model {lm.model} via {lm._resolve()['kind']})\n\n{table(rows)}\n")
    (Path(__file__).resolve().parent.parent / "results" / "synthetic.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
