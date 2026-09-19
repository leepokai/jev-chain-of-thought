"""Multiple choice as one Jev signature: the options are listed in the question text, the answer is a letter (or Yes/No)."""
from __future__ import annotations

from typing import Annotated, Literal

import dspy

from dspy_jev import Criteria


def mcq_signature(letters: list[str], instructions: str, question_desc: str = "Which option is correct?"):
    """`question -> answer: Literal[letters]`, options expected inside the question text (BBH / MMLU-Pro format)."""
    crit = Criteria(**{l: (f"option ({l}) as listed in the question" if len(l) == 1 else l) for l in letters})
    sig = dspy.Signature({"question": dspy.InputField(), "answer": dspy.OutputField(desc=question_desc)}, instructions)
    return sig.with_updated_fields("answer", type_=Annotated[Literal[tuple(letters)], crit])


def mcq_signature_criteria(letters: list[str], instructions: str, question_desc: str = "Which option is correct?"):
    """`question, answer_options -> answer`: the options travel as per-example criteria (option text as the description), not as state."""
    sig = dspy.Signature({"question": dspy.InputField(), "answer_options": dspy.InputField(), "answer": dspy.OutputField(desc=question_desc)}, instructions)
    return sig.with_updated_fields("answer", type_=Literal[tuple(letters)])


def with_options(question: str, options: dict[str, str]) -> str:
    if all(k == v for k, v in options.items()):  # Yes/No, True/False: the options are the answers themselves
        return f"{question}\nOptions:\n" + "\n".join(f"- {k}" for k in options)
    return f"{question}\nOptions:\n" + "\n".join(f"({k}) {v}" for k, v in options.items())
