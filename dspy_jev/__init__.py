"""dspy-jev: TypeSafe's Jev as a DSPy language model, plus prompting techniques that survive a model that never generates text."""
from .adapter import DRAFT_NOTE, Criteria, JevAdapter, Levels, Predict, last_answers, render
from .lm import JevLM, backend
from .modules import S2A, Chain, CoVe, Permute, Reread, SelfRefine

__all__ = ["JevLM", "JevAdapter", "Predict", "Criteria", "Levels", "last_answers", "backend", "render", "DRAFT_NOTE", "SelfRefine", "Chain", "Reread", "CoVe", "S2A", "Permute", "configure"]


def configure(**lm_kwargs):
    """`dspy.configure(lm=JevLM(**lm_kwargs), adapter=JevAdapter())`, returned for chaining."""
    import dspy
    lm = JevLM(**lm_kwargs)
    dspy.configure(lm=lm, adapter=JevAdapter())
    return lm
