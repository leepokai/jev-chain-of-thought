"""Shared pieces for the benchmark scripts: the technique zoo, a hashed bag-of-words embedder for KNNFewShot, tables, cost."""
from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from pathlib import Path
from typing import Literal, get_origin

import dspy
import numpy as np

import dspy_jev
from dspy_jev import S2A, CoVe, Permute, Predict, Reread, SelfRefine

RESULTS = Path(__file__).resolve().parent.parent / "results"
PRICE = 0.042 / 1e6  # $ per input token (jev-1.13; output tokens are free)

PHRASES = {
    "role": "You are a meticulous domain expert; answer as the expert would.",
    "emotion": "This is very important to my career. Take a deep breath and be careful: a wrong answer has real consequences.",
    "zs-cot": "Let's think step by step before deciding.",
}


def configure(threads: int = 16, **kw):
    """JevLM + JevAdapter, gateway or direct from the environment; returns the LM."""
    lm = dspy_jev.configure(**kw)
    dspy.configure(lm=lm, adapter=dspy_jev.JevAdapter())
    return lm


def hashed_bow(texts: list[str], dim: int = 4096) -> np.ndarray:
    """Cheap lexical embedder for dspy.KNNFewShot: hashed unigram counts, L2-normalised."""
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for i, t in enumerate(texts):
        for w in re.findall(r"[a-z0-9]+", str(t).lower()):
            out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1
        n = np.linalg.norm(out[i]) or 1
        out[i] /= n
    return out


def techniques(sig, trainset: list[dspy.Example], *, text_field: str, k: int = 5, many: int = 50, exemplars: list[dspy.Example] | None = None,
               permute: bool = True, s2a: bool = True) -> dict[str, dspy.Module]:
    """Every prompting technique as a DSPy program over one signature. `exemplars` (if given) are the official few-shot examples; else `trainset` is the pool."""
    has_choice = any(get_origin(f.annotation) is Literal for f in sig.output_fields.values())
    pool = exemplars or trainset
    zoo: dict[str, dspy.Module] = {"direct": Predict(sig)}
    for name, phrase in PHRASES.items():
        zoo[name] = Predict(sig.with_instructions(f"{sig.instructions}\n\n{phrase}".strip()))
    zoo["reread"] = Reread(sig, text_field)
    if has_choice and permute:
        zoo["permute"] = Permute(sig, n=3)
    zoo["fewshot"] = dspy.LabeledFewShot(k=k).compile(Predict(sig), trainset=pool, sample=exemplars is None)
    if exemplars and any("worked_solution" in e for e in exemplars):
        zoo["fewshot-cot"] = dspy.LabeledFewShot(k=k).compile(Predict(sig), trainset=exemplars, sample=False)
    if len(trainset) >= many:
        zoo["manyshot"] = dspy.LabeledFewShot(k=many).compile(Predict(sig), trainset=trainset)
    zoo["knn"] = dspy.KNNFewShot(k=k, trainset=trainset, vectorizer=dspy.Embedder(hashed_bow), max_bootstrapped_demos=0, max_labeled_demos=k).compile(Predict(sig))
    zoo["refine"] = SelfRefine(sig, rounds=2)
    zoo["cove"] = CoVe(sig)
    if s2a:
        zoo["s2a"] = S2A(sig, text_field)
    return zoo


def exact(field: str):
    def metric(example, pred, trace=None, pred_name=None, pred_trace=None):
        return float(pred[field] == example[field])
    return metric


def feedback_metric(field: str):
    """GEPA metric: score plus a one-line explanation of the miss."""
    def metric(example, pred, trace=None, pred_name=None, pred_trace=None):
        ok = pred[field] == example[field]
        return dspy.Prediction(score=float(ok), feedback="Correct." if ok else f"Wrong: expected {example[field]!r}, answered {pred[field]!r}.")
    return metric


class Meter:
    """Calls and input tokens the LM made since the meter was started."""

    def __init__(self, lm):
        self.lm, self.start = lm, len(lm.history)

    def read(self) -> tuple[int, int]:
        h = self.lm.history[self.start:]
        return len(h), sum((e.get("usage") or {}).get("prompt_tokens", 0) if isinstance(e, dict) else getattr(getattr(e, "response", None), "usage", None).prompt_tokens or 0 for e in h)


def evaluate(program, devset, metric, threads=16) -> float:
    return dspy.Evaluate(devset=devset, metric=metric, num_threads=threads, display_progress=False, failure_score=0.0)(program).score


def table(rows: list[dict]) -> str:
    h = list(rows[0])
    return "\n".join(["| " + " | ".join(h) + " |", "| " + " | ".join("---" for _ in h) + " |"] + ["| " + " | ".join(str(r.get(k, "")) for k in h) + " |" for r in rows])


def write(name: str, md: str):
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / name).write_text(md)
    print(md)


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)
