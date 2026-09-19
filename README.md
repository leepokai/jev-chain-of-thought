# LLM prompt techniques on Jev

**Every LLM prompting technique that survives a model that never generates text, ported to [TypeSafe's Jev](https://typesafe.ai) as a [DSPy](https://dspy.ai) extension and measured on BIG-Bench Hard, LegalBench, MMLU-Pro and CLERC.**

```bash
pip install dspy-jev
```

Jev is a *System One* model: it answers typed questions (`choice`, `noul`, `score`) about a `state` with calibrated probabilities, never writing a token. That makes it ~100× cheaper than an LLM judge and removes the whole "parse the model's prose" step, but it also means most prompting literature does not apply as written: there is no scratchpad, no sampling, no self-generated reasoning. This repo answers two questions with measurements rather than opinions: **which techniques still do something for Jev, and how do you run them without inventing a framework.** The answer to the second is DSPy: `dspy-jev` is a `BaseLM` and an `Adapter`, so signatures, `Evaluate`, `LabeledFewShot`, `KNNFewShot`, `MIPROv2` and `GEPA` all work on Jev unchanged.

## Results in one table

One model (`typesafe-ai/jev` = jev-1.13, September 2026), every technique on every item, all runs through `dspy.Evaluate` with the scripts in [`benchmarks/`](benchmarks). Full tables per benchmark are in [`results/`](results).

| benchmark | plain Jev | best technique | what worked |
| --- | --- | --- | --- |
| **LegalBench** rule application, 8 tasks, test splits ([table](results/legalbench.md)) | diversity_5 81.3 · diversity_6 82.0 · hearsay 68.0 | **GEPA-optimized instructions 100.0 · 96.0** ([optimize.md](results/optimize.md)); many-shot 94.7 on diversity_5; chain / code 85–91 · 87–88 · 76–78 | information-carrying techniques: 50 labelled cases, the statute's sub-conditions as facts, or an optimizer that rewrites the instructions |
| **BIG-Bench Hard**, 23 tasks × 100 items ([table](results/bbh.md), [criteria formulation](results/bbh-criteria.md)) | 91.3 mean (options as criteria) | 91.9 with one self-refine pass | nothing else moves the mean; few-shot fixes disambiguation_qa and hurts object tracking |
| **MMLU-Pro**, 500-question stratified test split ([criteria](results/mmlu-pro-criteria.md), [text](results/mmlu-pro.md)) | **82.2** with options as criteria, 76.4 with options in the question text | 82.6 (zs-CoT phrase, noise) | *where the options go* is worth 5.8 points; every prompting technique is within ±0.6; exemplars cost 2–5 |
| **CLERC** legal re-ranking, TypeSafe's cookbook slice ([table](results/clerc.md)) | one noul per pair, 30 calls/query (the cookbook's method) | one call per query: fanout or listwise | same ranking quality at 3% of the calls |
| **Synthetic rubric memos**, 100 docs, three dependent questions ([table](results/synthetic.md)) | 72 all-three-correct | **89** chain + refine | the second question depends on the first's answer; feeding answers back is the only way it can see it |

### The one-line verdicts

- **Jev has no scratchpad, so "reason harder" prompts do nothing.** Role prompting, emotional stimuli, "let's think step by step", chain-of-verification, self-consistency over option orders, prompt ensembles, majority votes: on every benchmark they sit within noise of plain Jev. A model that reads once and answers has nowhere to put the extra words.
- **Techniques that put information in front of the model do work, when the task lacks it.** A rule with sub-conditions answered first (`Chain`), fifty labelled precedents (`LabeledFewShot(k=50)`), or a task definition rewritten by an optimizer (`GEPA`): diversity_5 goes from 81 to 85–100, diversity_6 from 82 to 87–96, the synthetic rubric from 72 to 89. On tasks Jev already solves from the question alone (BBH at 91%, MMLU-Pro knowledge questions) the same techniques are neutral or negative: exemplars about *other* problems dilute the one being asked.
- **Automatic prompt optimization is the strongest single technique measured here**, and it is the newest. GEPA (2025) with Claude as the reflection model and Jev as the task model rewrote a one-sentence statute into instructions that score 100% and 96% on the two hardest diversity tasks, for ~730 Jev calls (a few cents) per task. It did nothing on hearsay, where the validation split is 14 rows.
- **How you formulate the question matters more than any technique.** Options as the `choice` criteria instead of text inside the state: +5.8 on MMLU-Pro. Sub-conditions as separate `noul`s instead of one conclusion: +4 to +10 on LegalBench. This is the part of "prompt engineering" that survives for Jev: the *shape* of the question, not the words around it.
- **Self-refine is safe but small.** Feeding the draft back never hurts by more than a point and pays only where answers depend on each other (memos +14, disambiguation +10). It converges in one round.


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

## Benchmarks in detail

### LegalBench: rule application

[LegalBench](https://hazyresearch.stanford.edu/legalbench/) (Guha et al., NeurIPS 2023) has tasks where the answer is a statute applied to facts: *diversity jurisdiction* holds when the parties are completely diverse **and** the amount in controversy exceeds $75,000; *hearsay* is an out-of-court statement **and** offered for its truth; *personal jurisdiction* is domicile **or** (minimum contacts **and** a claim arising from them). Per task the first rows are the demo pool / optimizer train and validation split; accuracy is on the held-out test split. [`benchmarks/legalbench.py`](benchmarks/legalbench.py), [`results/legalbench.md`](results/legalbench.md):

| task | n | direct | role | emotion | zs-CoT | re-read | few-shot (5) | many-shot (50) | kNN (5) | refine | CoVe | S2A | **chain** | **code** | **GEPA** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diversity_3 | 150 | 93.3 | 92.0 | 93.3 | 92.7 | 92.7 | 92.7 | 92.7 | 92.7 | 92.0 | 90.7 | 93.3 | 92.0 | 91.3 | |
| diversity_4 | 150 | 98.7 | 98.7 | 98.0 | 98.7 | 99.3 | 99.3 | 99.3 | 100 | 96.7 | 95.3 | 95.3 | 95.3 | 95.3 | |
| diversity_5 | 150 | 81.3 | 82.7 | 79.3 | 83.3 | 59.3 | 88.7 | **94.7** | 93.3 | 79.3 | 72.7 | 81.3 | 85.3 | 90.7 | **100.0** |
| diversity_6 | 150 | 82.0 | 86.0 | 89.3 | 86.0 | 85.3 | 86.0 | 84.7 | 84.0 | 82.7 | 79.3 | 78.7 | 88.0 | 87.3 | **96.0** |
| hearsay | 50 | 68.0 | 70.0 | 74.0 | 70.0 | 72.0 | 68.0 | 72.0 | 74.0 | 68.0 | 70.0 | 68.0 | **78.0** | 76.0 | 68.0 |
| personal_jurisdiction | 30 | 90.0 | 93.3 | 90.0 | 90.0 | 90.0 | 86.7 | 90.0 | 86.7 | 90.0 | 90.0 | 83.3 | 90.0 | 90.0 | |
| calls / row | | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 3 | 1.9 | 2 | 1 | 1 |

(diversity_1 and 2 are 100% for every column and omitted.) Three techniques carry information the question lacks and all three win on the hard tasks: many-shot (fifty labelled cases, one call: diversity_5 94.7), decomposition (`Chain` asks the two sub-conditions first; `code` applies the statute in Python to the same two answers), and GEPA, which rewrites the instructions from the training split and reaches 100 / 96 on the diversity tasks it was given. The wording techniques move ±3 points, which at n=150 is noise. Two are actively harmful on diversity_5: re-reading (59.3) and chain-of-verification (72.7). Sub-condition accuracy for `chain`/`code` (gold labels ship with the dataset): parties diverse 90–100%, amount in controversy 89–100%.

For scale, the LegalBench paper's Table 59 reports GPT-4 correctness of 76.6 on diversity_5, 80.0 on diversity_6, 75.5 on hearsay and 94.0 on personal jurisdiction (2023, their prompts, manually graded, on 300-row task sets); Jev's chain, many-shot and GEPA numbers above are on 150-row test splits of the same tasks, so they are comparable in kind but not a controlled comparison.

### MMLU-Pro: the question's shape beats every technique

[`benchmarks/mmlu_pro.py`](benchmarks/mmlu_pro.py) runs the same 500 held-out questions of a category-stratified 700-question sample under two formulations of the same signature:

| formulation | direct | role | emotion | zs-CoT | re-read | permute (3) | few-shot (5) | few-shot CoT | many-shot (50) | kNN | refine | CoVe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| options as `choice` criteria (`answer_options` input) | **82.2** | 81.6 | 82.0 | 82.6 | 81.8 | 82.2 | 79.6 | 79.6 | 77.6 | 80.4 | 82.0 | 81.6 |
| options as text inside the question | 76.4 | 76.6 | 77.2 | 77.2 | 78.4 | 76.4 | 74.2 | 74.2 | 74.8 | 74.2 | 76.0 | 76.8 |

Where the options go is worth 5.8 points; no prompting technique is worth more than 0.6 in either formulation, and exemplars (the dataset's own CoT examples, fifty labelled questions, or five nearest neighbours) cost 2 to 5. An [independent probe](https://archerhume.com/posts/jevs-architecture-unmasked/) reported 84.6% on its own MMLU-Pro sample; the first pass of this work measured 82.8% on the full 12,032-question test set with options as criteria ([results/first-pass-js](results/first-pass-js)).

### BIG-Bench Hard: solved without chain-of-thought

[BIG-Bench Hard](https://github.com/suzgunmirac/BIG-Bench-Hard) is where chain-of-thought prompting first showed its large effect (Codex: 56.6% answer-only → 73.9% with CoT; average human rater 67.7%). [`benchmarks/bbh.py`](benchmarks/bbh.py) runs the 23 option-answer tasks, 100 test items each, with the official three exemplars from the repo's prompt files as the few-shot demos ([`results/bbh.md`](results/bbh.md); [`bbh-criteria.md`](results/bbh-criteria.md) for the criteria formulation).

<!-- BBH-TABLE -->

Plain Jev averages 91.3% with one call and no reasoning (options as criteria) and the mean does not move under any technique except a self-refine pass (+0.6). The tasks chain-of-thought was invented for (object tracking, webs of liars, ordering constraints) are at 86–100% from a single read. What moves individual tasks: exemplars lift disambiguation_qa (a label-definition problem) and lower object tracking (examples about other shuffles distract), exactly as in the first pass.

### CLERC: TypeSafe's own re-ranking cookbook

TypeSafe's [re-ranking cookbook](https://docs.typesafe.ai/cookbooks/rerank_typesafe) scores 40 legal queries against a BM25 shortlist of 30 passages with one `noul` per pair (30 calls per query) and reports top-1 18%, top-5 35%, top-10 62% on jev-1.12. [`benchmarks/clerc.py`](benchmarks/clerc.py) rebuilds that slice exactly (BM25 alone: 5 / 15 / 38, as in the cookbook) plus the other 110 pooled rows, and tries three formulations that need one or two calls per query: *fanout* (the query as state, each candidate inside its own isolated noul), *listwise* (one `choice` over the 30 ids), and *cot* (fanout, then listwise over the top 10 with the fanout scores as established facts).

| subset | method | calls / query | top-1 | top-5 | top-10 | MRR |
| --- | --- | --- | --- | --- | --- | --- |
| cookbook 40 | BM25 only | 0 | 5.0 | 15.0 | 37.5 | 0.155 |
| cookbook 40 | TypeSafe cookbook, jev-1.12, one noul per pair | 30 | 18 | 35 | 62 | — |
| cookbook 40 | fanout (one call, 30 isolated nouls) | 1 | 30.0 | 55.0 | 65.0 | 0.416 |
| cookbook 40 | listwise (one choice over 30 ids) | 1 | 32.5 | 60.0 | **85.0** | **0.437** |
| cookbook 40 | cot (fanout → listwise over the top 10 with the scores as facts) | 2 | 32.5 | 47.5 | 65.0 | 0.412 |
| all 150 | BM25 only | 0 | 4.7 | 19.3 | 28.7 | 0.142 |
| all 150 | fanout | 1 | 26.0 | 54.0 | 68.0 | 0.388 |
| all 150 | listwise | 1 | 24.7 | 56.0 | **77.3** | 0.394 |
| all 150 | cot | 2 | 26.7 | 56.7 | 68.0 | **0.398** |

One call per query matches or beats the cookbook's thirty (the first pass measured the cookbook's own pointwise method on jev-1.13 at MRR 0.378 on the 150 queries; a paired bootstrap put every one-call variant within noise of it). Most of the jump over the published 18 / 35 / 62 is the model version, not the formulation; what the formulation buys is the cost: 3% of the calls and about half the tokens.

### Automatic prompt optimization

[`benchmarks/optimize.py`](benchmarks/optimize.py) runs `dspy.GEPA` (reflective prompt evolution, Agrawal et al. 2025) and `dspy.MIPROv2` on a one-call Jev program with Claude Sonnet 4.5 (through Vercel AI Gateway) as the reflection / proposal model and Jev as the task model. GEPA's `auto="light"` budget spent about 730 Jev calls per LegalBench task.

<!-- OPTIMIZE-TABLE -->

The optimized instructions are saved under [`results/optimized/`](results/optimized). On diversity_5 GEPA turned the one-sentence statute into a procedure (enumerate plaintiff–defendant pairs, check citizenship overlap, sum each plaintiff's claims against each defendant, compare to $75,000) and the test score went from 81.3 to 100.0.

### Synthetic rubric memos

[`benchmarks/synthetic.py`](benchmarks/synthetic.py): 100 OCR-noised transaction memos and a three-question rubric whose second question ("needs review?") is defined in terms of the first ("risk level"). Direct 72% all-three-correct → self-refine 86 → chain (the rubric's three inputs first) 85 → chain + refine 89. Within one Jev call the questions cannot see each other; a second call with the first answers in the state is the only way the dependency can be honoured.

### What was tried and did not survive

- Typed step-by-step chains on BBH (one call per swap for object tracking, one person per step for webs of lies): 80–84% against 90–98% direct in the first pass; each step is a new place to be wrong and the model was already solving the whole thing in one read.
- Composite "facet" scoring on CLERC (three extra nouls per pair averaged in log-odds): −0.12 MRR in the first pass; one well-written question beats a committee of weaker ones.
- Feeding back a draft from a *different* document: Jev copies a wrong draft field about a third of the time (first pass). The draft must be its own answer to the same document.


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
