# LLM prompt techniques on Jev

**Every LLM prompting technique that survives a model that never generates text, ported to [TypeSafe's Jev](https://typesafe.ai) as a [DSPy](https://dspy.ai) extension and measured on BIG-Bench Hard, LegalBench, MMLU-Pro and CLERC.**

```bash
pip install dspy-jev
```

Jev is a *System One* model: it answers typed questions (`choice`, `noul`, `score`) about a `state` with calibrated probabilities, never writing a token. That makes it ~100× cheaper than an LLM judge and removes the whole "parse the model's prose" step, but it also means most prompting literature does not apply as written: there is no scratchpad, no sampling, no self-generated reasoning. This repo answers two questions with measurements rather than opinions: **which techniques still do something for Jev, and how do you run them without inventing a framework.** The answer to the second is DSPy: `dspy-jev` is a `BaseLM` and an `Adapter`, so signatures, `Evaluate`, `LabeledFewShot`, `KNNFewShot`, `MIPROv2` and `GEPA` all work on Jev unchanged.

<!-- RESULTS -->

## Use it

```python
from typing import Annotated, Literal
import dspy, dspy_jev
from dspy_jev import Criteria, Levels, Predict, SelfRefine, Chain

dspy_jev.configure()            # JevLM + JevAdapter; key from JEV_API_KEY / TYPESAFE_API_KEY, AI_GATEWAY_API_KEY or VERCEL_OIDC_TOKEN

class Memo(dspy.Signature):
    """Risk = amount points + origin points + note points. HIGH if >= 4, MEDIUM 2-3, LOW otherwise."""   # -> the question's `task`
    memo: str = dspy.InputField()                                                                        # -> the `state`
    risk: Annotated[Literal["HIGH", "MEDIUM", "LOW"], Criteria(HIGH="score >= 4", MEDIUM="2-3", LOW="<= 1")] = dspy.OutputField(desc="Risk level.")  # -> choice
    review: bool = dspy.OutputField(desc="Needs manual review?")                                          # -> noul
    severity: Annotated[float, Levels("no harm", "minor", "major")] = dspy.OutputField()                 # -> score

pred = Predict(Memo)(memo="Origin: Iran. Amount: USD 80,174. Notes: routine invoice.")
pred.risk, pred.review, pred.severity      # 'HIGH', True, 1.9
pred.jev["risk"]["probabilities"]          # {'HIGH': 0.88, 'MEDIUM': 0.12, 'LOW': 0.0}, plus 'confidence'
```

The adapter maps a signature to one Jev call: `bool` → `noul`, `Literal[...]` → `choice`, `Annotated[float, Levels(...)]` → `score`; input fields become the state, the docstring the task, field `desc` the question, and DSPy demos go in as structured `examples`. `Predict` is `dspy.Predict` plus `.jev` (raw probabilities and confidence). Anything else in DSPy is unchanged:

```python
program = dspy.LabeledFewShot(k=5).compile(Predict(Memo), trainset=train)          # few-shot
program = dspy.KNNFewShot(k=5, trainset=train, vectorizer=dspy.Embedder(embed), max_bootstrapped_demos=0).compile(Predict(Memo))
score   = dspy.Evaluate(devset=test, metric=lambda ex, p, trace=None: p.risk == ex.risk, num_threads=16)(program)
better  = dspy.GEPA(metric=metric_with_feedback, auto="light", reflection_lm=dspy.LM("openai/anthropic/claude-sonnet-4.5", api_base=..., api_key=...)).compile(program, trainset=train, valset=val)
```

The techniques that need a second call are modules:

| module | technique | what it does |
| --- | --- | --- |
| `SelfRefine(sig, rounds=2)` | self-refine | ask, feed the rendered draft back as `draft_answers`, ask again until the labels stop changing |
| `Chain(facts_sig, sig, refine=0)` | chain of thought / least-to-most | each step's answers become `established_facts` for the next; intermediate answers travel with the prediction |
| `Reread(sig)` | Re2 | the text input included twice |
| `CoVe(sig)` | chain-of-verification | draft → one "is the draft correct?" noul → final with both |
| `S2A(sig)` | System 2 Attention, typed | one relevance noul per sentence, then the question over the sentences kept |
| `Permute(sig, n=3)` | self-consistency for a deterministic model | the same choice under `n` option orders, probabilities averaged |

Two backends, same client: TypeSafe's API (`JEV_API_KEY`, or `jev-guard key`) and Vercel AI Gateway (`AI_GATEWAY_API_KEY`, or `VERCEL_OIDC_TOKEN` from `vercel env pull`). Responses go through `dspy.cache` (memory + disk), so re-running a benchmark is free.

<!-- BENCH -->

## Reproduce

```bash
git clone https://github.com/leepokai/llm-prompt-techniques-on-jev && cd llm-prompt-techniques-on-jev
python -m venv .venv && .venv/bin/pip install -e ".[bench,test]"
.venv/bin/pytest -q                                   # no key needed
export VERCEL_OIDC_TOKEN=…                            # or JEV_API_KEY
.venv/bin/python benchmarks/synthetic.py              # 100 memos × 4 strategies                     ≈ $0.04
.venv/bin/python benchmarks/legalbench.py             # 8 tasks × 15 techniques on the test splits    ≈ $0.8
.venv/bin/python benchmarks/bbh.py                    # 23 tasks × 14 techniques, 100 test items each ≈ $1.5
.venv/bin/python benchmarks/mmlu_pro.py               # 500 test questions × 13 techniques            ≈ $0.4
.venv/bin/python benchmarks/clerc.py                  # cookbook slice, 3 formulations                ≈ $0.3
.venv/bin/python benchmarks/optimize.py               # GEPA + MIPROv2 on five tasks (reflection LM via the gateway)
```

Datasets download to `data/` on first use (Hugging Face for LegalBench, MMLU-Pro and CLERC; the BBH repo for tasks and prompt files). Each script writes a Markdown table and a JSON of per-technique scores to `results/`. The first pass of this work was a hand-written Node harness; its measurements are kept under [`results/first-pass-js/`](results/first-pass-js) for reference.

## Related

- [jev-guard](https://github.com/leepokai/jev-guard) — the same author's prompt-injection and dangerous-action guard for coding agents, built on Jev.
- [TypeSafe docs](https://docs.typesafe.ai) · [re-ranking cookbook](https://docs.typesafe.ai/cookbooks/rerank_typesafe) · [DSPy](https://dspy.ai) · [GEPA](https://arxiv.org/abs/2507.19457) · [Jev's architecture unmasked](https://archerhume.com/posts/jevs-architecture-unmasked/)

MIT © [leepokai](https://github.com/leepokai)
