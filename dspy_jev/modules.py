"""Prompting techniques as DSPy modules, for a model that answers typed questions and never generates text."""
from __future__ import annotations

import random
import re
from typing import Annotated, Literal, get_args, get_origin

import dspy

from .adapter import DRAFT_NOTE, Criteria, Predict, render

FACTS_NOTE = "Answers established in a previous pass."


DRAFT_FIELD, FACTS_FIELD = "draft_answers", "established_facts"


def with_draft(signature, note: str = DRAFT_NOTE):
    return signature.append(DRAFT_FIELD, dspy.InputField(desc=note), type_=str)


def with_facts(signature, note: str = FACTS_NOTE):
    return signature.append(FACTS_FIELD, dspy.InputField(desc=note), type_=str)


class SelfRefine(dspy.Module):
    """Ask, feed the draft back as an extra input, ask again; stop when the labels stop changing (at most `rounds` extra passes)."""

    def __init__(self, signature, rounds: int = 2):
        self.first = Predict(signature)
        self.again = Predict(with_draft(signature))
        self.rounds = rounds
        self.outputs = list(dspy.ensure_signature(signature).output_fields)

    def forward(self, **kwargs):
        pred = self.first(**kwargs)
        for _ in range(self.rounds):
            nxt = self.again(**kwargs, **{DRAFT_FIELD: render(pred.jev)})
            same = all(nxt[k] == pred[k] for k in self.outputs)
            pred = nxt
            if same:
                break
        return pred


class Chain(dspy.Module):
    """Chain of facts: each step's answers are rendered into a `facts` input of the next step; the last step's outputs are returned."""

    def __init__(self, *signatures, refine: int = 0):
        sigs = [dspy.ensure_signature(s) for s in signatures]
        self.steps = [Predict(sigs[0])] + [Predict(with_facts(s)) for s in sigs[1:]]
        self.refine = refine
        self.again = Predict(with_draft(with_facts(sigs[-1]))) if refine and len(sigs) > 1 else None
        self.outputs = list(sigs[-1].output_fields)

    def forward(self, **kwargs):
        facts, pred, steps = [], None, []
        for i, step in enumerate(self.steps):
            pred = step(**kwargs) if i == 0 else step(**kwargs, **{FACTS_FIELD: "\n".join(facts)})
            facts.append(render(pred.jev))
            steps.append(pred)
        for _ in range(self.refine if self.again else 0):
            nxt = self.again(**kwargs, **{FACTS_FIELD: "\n".join(facts[:-1]), DRAFT_FIELD: render(pred.jev)})
            same = all(nxt[k] == pred[k] for k in self.outputs)
            pred = nxt
            if same:
                break
        for p in steps[:-1]:  # intermediate answers travel with the final prediction
            for k, v in p.items():
                if k not in pred and k != "jev":
                    pred[k] = v
        return pred


class Reread(dspy.Module):
    """Re2 (Xu et al. 2023): the text input is included twice."""

    def __init__(self, signature, field: str | None = None):
        sig = dspy.ensure_signature(signature)
        self.field = field or next(iter(sig.input_fields))
        self.predict = Predict(sig)

    def forward(self, **kwargs):
        v = kwargs[self.field]
        return self.predict(**{**kwargs, self.field: f"{v}\n\nRead the question again:\n{v}"})


class CoVe(dspy.Module):
    """Chain-of-verification: draft, one 'is the draft correct?' noul, then the final answer with both in the state."""

    def __init__(self, signature):
        sig = dspy.ensure_signature(signature)
        self.draft = Predict(sig)
        check_sig = dspy.Signature({**{k: dspy.InputField() for k in sig.input_fields}, DRAFT_FIELD: dspy.InputField(desc=DRAFT_NOTE),
                                    "draft_correct": dspy.OutputField(desc="Is the draft answer correct? Check it against the evidence step by step.")},
                                   sig.instructions)
        check_sig = check_sig.with_updated_fields("draft_correct", type_=bool)
        self.check = Predict(check_sig)
        self.final = Predict(with_draft(sig))

    def forward(self, **kwargs):
        d = self.draft(**kwargs)
        c = self.check(**kwargs, **{DRAFT_FIELD: render(d.jev)})
        return self.final(**kwargs, **{DRAFT_FIELD: render(d.jev) + "\n" + render(c.jev)})


class S2A(dspy.Module):
    """System 2 Attention, typed: one relevance noul per sentence, then the question over the sentences kept."""

    def __init__(self, signature, field: str | None = None, keep_at_least: int = 1):
        sig = dspy.ensure_signature(signature)
        self.field = field or next(iter(sig.input_fields))
        self.sig = sig
        self.predict = Predict(sig)
        self.keep_at_least = keep_at_least

    def forward(self, **kwargs):
        text = kwargs[self.field]
        sents = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
        if len(sents) < 3:
            return self.predict(**kwargs)
        fields = {"text": dspy.InputField(), "question": dspy.InputField()}
        fields.update({f"s{i}_relevant": dspy.OutputField(desc=f"Is this sentence needed to answer the question? Sentence: {s}") for i, s in enumerate(sents)})
        sig = dspy.Signature(fields, "Decide which sentences of the text are needed to answer the question.")
        for i in range(len(sents)):
            sig = sig.with_updated_fields(f"s{i}_relevant", type_=bool)
        rel = Predict(sig)(text=text, question="; ".join(f.description or n for n, f in self.sig.output_fields.items()))
        ranked = sorted(range(len(sents)), key=lambda i: -rel.jev[f"s{i}_relevant"]["p"])
        keep = {i for i in range(len(sents)) if rel[f"s{i}_relevant"]} | set(ranked[: self.keep_at_least])
        return self.predict(**{**kwargs, self.field: " ".join(s for i, s in enumerate(sents) if i in keep)})


class Permute(dspy.Module):
    """Self-consistency for a deterministic model: the same choice question under `n` option orders, probabilities averaged."""

    def __init__(self, signature, n: int = 3, seed: int = 0):
        self.sig = dspy.ensure_signature(signature)
        self.n, self.seed = n, seed
        self.field = next(k for k, f in self.sig.output_fields.items() if get_origin(f.annotation) is Literal)
        self.predicts = [Predict(self._permuted(i)) for i in range(n)]

    def _permuted(self, i):
        if i == 0:
            return self.sig
        f = self.sig.output_fields[self.field]
        opts = list(get_args(f.annotation))
        random.Random(self.seed + i).shuffle(opts)
        crit = next((m for m in f.metadata if isinstance(m, Criteria)), None)
        t = Literal[tuple(opts)]
        return self.sig.with_updated_fields(self.field, type_=Annotated[t, crit] if crit else t)

    def forward(self, **kwargs):
        preds = [p(**kwargs) for p in self.predicts]
        probs = {}
        for p in preds:
            for o, v in p.jev[self.field]["probabilities"].items():
                probs[o] = probs.get(o, 0) + v / len(preds)
        best = max(probs, key=probs.get)
        by_str = {str(v): v for v in get_args(self.sig.output_fields[self.field].annotation)}
        out = preds[0]
        out[self.field] = by_str.get(best, best)
        out.jev = {**out.jev, self.field: {"choice": best, "probabilities": probs}}
        return out
