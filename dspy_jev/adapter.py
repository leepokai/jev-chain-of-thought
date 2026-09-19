"""JevAdapter: turns a DSPy signature into Jev's typed questions and Jev's answers back into output fields.

Output field types that Jev can answer:
  - `bool`                                            -> noul   (optional `Annotated[bool, Criteria(true=..., false=...)]`)
  - `Literal["a", "b", ...]`                          -> choice (optional `Annotated[Literal[...], Criteria(a="...", b="...")]`)
  - `Annotated[float, Levels("level 0", "level 1", …)]` -> score
Input fields become the `state` (one field: its value as is; several: an object keyed by field name). An input field named
`<choice_field>_options` (a dict option -> description) supplies per-example option descriptions for that choice and is not sent as state:
the model then sees only the options present in that example, described by their text.
The signature's instructions become `task`, each field's `desc` its question, and few-shot demos go in as `examples`.
`dspy_jev.Predict` (and every module here) attaches `pred.jev`: the raw answers with probabilities and confidence.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Literal, get_args, get_origin

import dspy
from dspy.adapters.base import Adapter
from dspy.signatures.signature import Signature, _default_instructions

DRAFT_NOTE = "Draft answers from a previous pass. They may contain errors: re-check each one against the evidence and correct it."


class Criteria(dict):
    """Option (choice) or true/false (noul) descriptions: `Annotated[Literal["a","b"], Criteria(a="…", b="…")]`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class Levels(list):
    """Score levels, lowest first: `Annotated[float, Levels("no harm", "minor", "major")]`."""

    def __init__(self, *levels):
        super().__init__(levels[0] if len(levels) == 1 and isinstance(levels[0], (list, tuple)) else levels)


_local = threading.local()


def last_answers() -> dict:
    """Raw Jev answers of the most recent call on this thread (probabilities, confidence)."""
    return getattr(_local, "last", {})


def _extra(field) -> dict:
    return getattr(field, "json_schema_extra", None) or {}


def _meta(field, cls):
    return next((m for m in getattr(field, "metadata", []) or [] if isinstance(m, cls)), None)


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip().capitalize() + "?"


def question_for(name: str, field, task: str | None, examples: list | None, options: dict | None = None) -> dict:
    """One Jev question for one output field. `options` overrides the choice criteria for this example."""
    ann, extra = field.annotation, _extra(field)
    desc = extra.get("desc") or field.description or _humanize(name)
    instr: dict[str, Any] = {"question": desc}
    if task:
        instr["task"] = task
    if examples:
        instr["examples"] = examples
    crit, levels = _meta(field, Criteria) or Criteria(), _meta(field, Levels)
    if ann is bool:
        return {"type": "noul", "instructions": instr, "criteria": {"true": crit.get("true", crit.get(True, "Yes.")), "false": crit.get("false", crit.get(False, "No."))}}
    if get_origin(ann) is Literal:
        if options:
            return {"type": "choice", "instructions": instr, "criteria": {str(v): str(d) for v, d in options.items()}}
        return {"type": "choice", "instructions": instr, "criteria": {str(v): crit.get(v, crit.get(str(v), str(v))) for v in get_args(ann)}}
    if levels is not None:
        return {"type": "score", "instructions": instr, "criteria": list(levels)}
    raise TypeError(f"JevAdapter cannot answer output field `{name}: {ann}`; use bool, Literal[...] or Annotated[float, Levels(...)]")


def render(answers: dict[str, dict]) -> str:
    """Answers as one line each, the way SelfRefine feeds them back."""
    lines = []
    for k, a in answers.items():
        if "choice" in a:
            probs = ", ".join(f"{o} {p:.2f}" for o, p in sorted((a.get("probabilities") or {}).items(), key=lambda x: -x[1]))
            lines.append(f"{k}: {a['choice']} ({probs})")
        elif "score" in a:
            lines.append(f"{k}: {a['score']:.2f}")
        else:
            lines.append(f"{k}: {str(a['p'] >= 0.5).lower()} (p={a['p']:.2f})")
    return "\n".join(lines)


class JevAdapter(Adapter):
    def format(self, signature: type[Signature], demos: list[dict[str, Any]], inputs: dict[str, Any]) -> list[dict[str, Any]]:
        opt_fields = {f"{o}_options": o for o in signature.output_fields if f"{o}_options" in signature.input_fields}
        in_names = [k for k in signature.input_fields if k not in opt_fields]
        state = inputs[in_names[0]] if len(in_names) == 1 else {k: inputs[k] for k in in_names if k in inputs}
        examples = [{"input": {k: d[k] for k in in_names if k in d}, "output": {k: v for k, v in d.items() if k not in in_names and k not in opt_fields and not k.startswith("_")}} for d in demos] or None
        task = (signature.instructions or "").strip() or None
        if task == _default_instructions(signature):  # DSPy's auto-generated "Given the fields …" carries no information
            task = None
        questions = {name: question_for(name, f, task, examples, inputs.get(f"{name}_options") if f"{name}_options" in opt_fields else None) for name, f in signature.output_fields.items()}
        return [{"role": "user", "content": json.dumps({"state": state, "questions": questions}, default=str)}]

    def parse(self, signature: type[Signature], completion: str) -> dict[str, Any]:
        answers = json.loads(completion)
        _local.last = answers
        out: dict[str, Any] = {}
        for name, field in signature.output_fields.items():
            a = answers.get(name)
            if a is None:
                continue
            ann = field.annotation
            if ann is bool:
                out[name] = a["p"] >= 0.5
            elif get_origin(ann) is Literal:
                by_str = {str(v): v for v in get_args(ann)}
                out[name] = by_str.get(a["choice"], a["choice"])
            else:
                out[name] = a["score"] if ann is not int else round(a["score"])
        return out


class Predict(dspy.Predict):
    """`dspy.Predict` whose predictions carry `.jev` (raw answers with probabilities and confidence)."""

    def forward(self, **kwargs):
        pred = super().forward(**kwargs)
        pred.jev = last_answers()
        return pred
