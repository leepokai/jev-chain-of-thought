# jev-chain-of-thought

**Chain-of-thought and self-refinement for [TypeSafe's Jev](https://typesafe.ai). Feed Jev's typed answers back as state and ask again.**

Jev is a *System One* model: it never generates text, it answers typed questions (`choice`, `noul`, `score`) about a `state` and returns calibrated probabilities. That makes it 100× cheaper than an LLM judge, but it also means it has no scratchpad. Every question in a request is scored on its own; a question cannot see what Jev answered to the question next to it, and Jev cannot revise an answer after seeing its own first draft.

This package adds the scratchpad in code: ask Jev, render its answers as text, put that text back into the state, ask again. Three primitives, zero dependencies, one fetch:

| primitive | what it does | when it helps |
| --- | --- | --- |
| `refine(state, questions)` | ask, feed the draft back, ask again until the labels stop changing | rubrics where one answer depends on another |
| `chain(state, [steps…, final])` | each step's answers become established facts for the next step | decompose a judgment into the facts it depends on |
| `choose(state, options)` / `rerank(query, candidates)` | ready-made chains for multiple choice and for ranking | MMLU-style questions, retrieval re-ranking |

## Results in one table

Three benchmarks, one model (`jev-1.13.0`, September 2026), every Jev response cached under [`bench/results/`](bench/results) so the tables re-render without a key.

| benchmark | plain Jev | jev-chain-of-thought | calls | what changed |
| --- | --- | --- | --- | --- |
| **Dependent rubric** — 100 transaction memos, 3 questions where `requires_review` depends on `risk_level` ([details](bench/results/synthetic.md)) | 74% all-3-correct | **93%** (`chain` + `refine`) | 3.1 / doc | the questions can finally see each other's answers |
| **CLERC legal re-ranking** — TypeSafe's own cookbook, replicated exactly ([details](bench/results/clerc-150.md)) | top-1 23% · MRR 0.378 · **30 calls/query** (the cookbook's method) | top-1 27% · MRR 0.402 · **2 calls/query** (`rerank`, fanout + listwise) | 7% of the calls, 72% of the tokens | same or better ranking at a fraction of the cost; the accuracy gain itself is within noise at n=150 |
| **MMLU-Pro** — full test set, 12,032 questions ([details](bench/results/mmlu-pro-all.md), 7 strategies on a 700-question sample [here](bench/results/mmlu-pro-700.md)) | **82.8%** (ECE 0.048, $0.29 for the whole set) | 82.9% (nothing beats plain Jev) | 1–3 / q | atomic knowledge questions have no intermediate answers to feed back |

The pattern: **feeding answers back helps exactly when one answer depends on another.** In a single Jev request every question is scored in isolation ([TypeSafe's own parallel-questions cookbook](https://docs.typesafe.ai/cookbooks/parallel_questions) shows batching "adds no noise" precisely because questions never see each other). A rubric whose review flag depends on the risk level, or a ranking whose listwise pick benefits from pointwise scores, gains from a second pass. A ten-option physics question does not.

### Against TypeSafe's published numbers

TypeSafe publishes its results as cookbooks. The one with a public dataset and a hard number is [re-ranking on CLERC](https://docs.typesafe.ai/cookbooks/rerank_typesafe): 40 legal queries, a BM25 shortlist of 30 from 3,565 court-opinion passages, one `noul` per query–candidate pair on `jev-1.12`.

`bench/clerc/prepare.py` rebuilds that slice byte-for-byte (same seed, same 170 pooled rows, same `bm25s` shortlist: BM25 alone lands the gold passage at rank 1 for 5%, top-5 15%, top-10 38%, exactly as the cookbook reports). On those 40 queries:

| method | calls / query | top-1 | top-5 | top-10 | cost (40 queries) |
| --- | --- | --- | --- | --- | --- |
| TypeSafe cookbook, `jev-1.12`, pointwise | 30 | 18% | 35% | 62% | $0.065 (their figure) |
| same method replicated on `jev-1.13.0` | 30 | 32.5% | 52.5% | 72.5% | $0.070 |
| `rerank` listwise (one `choice` over 30 ids) | **1** | 32.5% | 60.0% | **85.0%** | **$0.035** |
| `rerank` cot30 (pointwise draft → listwise over all 30) | 31 | **37.5%** | 60.0% | 75.0% | $0.106 |
| `rerank` default (fanout → listwise over top 10) | **2** | 32.5% | 60.0% | 75.0% | $0.051 |

Two honest caveats. Most of the jump over the cookbook's 18 / 35 / 62 comes from the model version, not from this package: the plain replica already scores 32.5 / 52.5 / 72.5 on `jev-1.13.0`. And 40 queries is too few to separate methods, so the bench also runs the other 110 pooled rows under the identical protocol (150 queries, [`clerc-150.md`](bench/results/clerc-150.md)): the 2-call default reaches MRR 0.402 vs 0.378 for the 30-call cookbook method, but a paired bootstrap puts that difference at +0.023 with a 95% interval of [−0.026, +0.062]. What *is* robust is the cost side: one or two calls per query, with the query sent once and the candidates inside isolated questions, match the 30-call design.

A decomposition that hurt: adding three extra "facet" nouls per pair (same rule? shared wording? authoritative language?) and averaging log-odds drops MRR by 0.12 with a confidence interval well below zero. Jev's single well-written question beats a composite of weaker ones. `rerank` keeps `facets` as an option; the bench keeps the negative result.

### Where the feedback loop wins outright

[`bench/synthetic`](bench/synthetic/run.mjs): 100 OCR-noised transaction memos with a written rubric. `risk_level` is a sum of amount, origin and note points; `requires_review` is true when risk is HIGH or MEDIUM or the note mentions a dispute; `action_tier` depends on risk and amount. Three questions, one document, gold labels computed by the generator.

| strategy | risk_level | requires_review | action_tier | all 3 | calls / doc |
| --- | --- | --- | --- | --- | --- |
| direct (one call) | 99% | 88% | 84% | 74% | 1 |
| `refine` (feed the draft back until it stops changing) | 100% | 99% | 89% | 88% | 2.2 |
| `chain` (ask the three rubric inputs first, then the judgment) | 100% | 93% | 88% | 87% | 2 |
| `chain` + `refine` | 100% | 97% | 94% | **93%** | 3.1 |

`requires_review` goes from 88% to 99% with one feedback pass, because its rubric is literally "look at `risk_level`" and in a single call it cannot. Convergence takes one round: the second and third passes change 4 and 3 answers out of 100.

**Wrong-draft control.** Feed back a draft taken from a *different* memo (wrong on 87 of 100) and the final answer copies a wrong field on 29 of them; all-3 accuracy drops from 74% to 66%. Jev treats the draft as evidence, so the loop only helps when the draft is Jev's own answer to the same document. Never feed it another model's guess or a stale result.

### Where it does not help

[`bench/mmlu-pro`](bench/mmlu-pro/run.mjs), 700 questions stratified over the 14 MMLU-Pro categories (50 each), options as `choice` criteria, the question and subject as state:

| strategy | accuracy | mean top-p | ECE | calls / q |
| --- | --- | --- | --- | --- |
| direct | **82.1%** | 0.840 | **0.059** | 1 |
| refine (own draft fed back) | 81.1% | 0.856 | 0.063 | 2 |
| permute (3 option orders averaged) | 81.9% | 0.829 | 0.052 | 3 |
| verify (+ one "is this option correct?" noul per option, fed back) | 82.1% | 0.861 | 0.073 | 2 |
| narrow (second choice over the top 3) | 80.9% | 0.829 | 0.076 | 2 |
| cot (verify + narrow) | 80.3% | 0.838 | 0.067 | 2 |
| product (listwise × per-option nouls, one call) | 82.3% | 0.867 | 0.073 | 1 |

Every variant lands within ±2 points of plain Jev (one question is 0.14 points). On the **full test set** ([`mmlu-pro-all.md`](bench/results/mmlu-pro-all.md)) plain Jev scores **82.8%** with ECE 0.048 for $0.29 and nine minutes at 6 concurrent calls; the one-call `product` ensemble scores 82.9%, a difference of 12 questions in 12,032. For reference, an [independent probe](https://archerhume.com/posts/jevs-architecture-unmasked/) reported 84.6% on its own MMLU-Pro sample. `choose()` therefore defaults to `strategy: "direct"`; the other strategies are there for tasks with structure, and for people who want to check for themselves.

Per category, full set, plain Jev: biology 91.6 · economics 88.4 · computer science 87.1 · math 87.1 · psychology 86.7 · physics 83.9 · philosophy 83.8 · health 81.8 · other 81.2 · chemistry 80.0 · business 79.2 · history 78.0 · law 77.3 · engineering 75.6.


## Install

```bash
npm install jev-chain-of-thought
export JEV_API_KEY=…        # or TYPESAFE_API_KEY, or `jev-guard key <key>`
```

Node ≥ 20.3. No dependencies. Works with the TypeSafe API directly (`POST https://api.typesafe.ai/v1/systemone`).

## Use

```js
import { ask, refine, chain, choose, rerank } from "jev-chain-of-thought";

// plain Jev
const { answers } = await ask(memo, questions);

// self-refine: ask, feed the draft back, ask again (stops at the fixed point, at most `rounds` extra calls)
const r = await refine(memo, questions, { rounds: 2 });
r.answers.risk_level.choice;   // "HIGH"
r.calls;                       // 2 — converged after one refinement

// chain of thought: ask the facts first, then the judgment with those facts in the state
const c = await chain(memo, [
  { amount_bucket: { type: "choice", instructions: "Which bracket is the amount in?", criteria: { large: ">= 50,000", mid: "10,000–49,999", small: "< 10,000" } } },
  { risk_level: { type: "choice", instructions: "Risk level under the rubric…", criteria: { HIGH: "…", MEDIUM: "…", LOW: "…" } } },
], { refine: 1 });

// multiple choice: listwise choice + one "is this option correct?" noul per option, then a second choice over the top 3 with that draft
const m = await choose({ question, subject: "physics" }, { A: "…", B: "…", C: "…", D: "…" }, { strategy: "cot", k: 3 });
m.choice; m.probabilities; m.calls;  // 2

// re-ranking: pointwise nouls, then one listwise choice over the top 10 with the pointwise scores as draft
const k = await rerank(query, { p1: "…", p2: "…", /* … */ }, { instructions: "Does the passage establish the proposition the query cites?", topK: 10 });
k.ranking;  // ids, best first
```

Every call returns `trace` (the raw Jev responses, with `usage` and `ms`) and `calls`. Pass `model: "jev-1.13.0"` to pin a version, `ask: myFetch` to inject a cached or mocked client.

### How the feedback looks

`feedback(state, answers)` renders answers as one line each and appends them to the state (a string gets a text block, an object gets a `draft_answers` key):

```
--- Draft answers from a previous pass. They may contain errors: re-check each one against the evidence and correct it. ---
risk_level: HIGH (HIGH 0.88, MEDIUM 0.12, LOW 0.00, NONE 0.00)
requires_review: true (p=0.91)
```

The wording matters: a draft presented as fact is copied, a draft presented as fallible is checked (see the anchor control below).

## Borrowing LLM prompting techniques

Every prompting trick that works on an LLM is a way of putting more useful text in front of the model before it commits. Jev cannot write that text itself, so the package (or your code) has to. What carries over, what it becomes here, and what it measured:

| LLM technique | What it becomes for Jev | Measured here |
| --- | --- | --- |
| Chain-of-thought ([Wei et al. 2022](https://arxiv.org/abs/2201.11903)) | `chain`: the intermediate steps are typed questions you author once per task; their answers become facts in the state | dependent rubric +13 pts (`chain`), +19 with `refine`; BBH typed chains below |
| Least-to-most ([Zhou et al. 2022](https://arxiv.org/abs/2205.10625)) | progressive state: feed the problem one step at a time, carrying the previous step's answers (BBH tracking: one call per swap) | BBH `tracking` column |
| Self-refine ([Madaan et al. 2023](https://arxiv.org/abs/2303.17651)) | `refine`: the draft goes back in as fallible evidence until the labels stop changing | rubric +14 pts; MMLU-Pro 0; BBH `refine` column |
| Self-consistency ([Wang et al. 2022](https://arxiv.org/abs/2203.11171)) | `choose({ strategy: "permute" })`: the same question under shuffled option orders, probabilities averaged (Jev is deterministic, so order is the only sampling axis) | MMLU-Pro −0.2 pts |
| Chain-of-verification ([Dhuliawala et al. 2023](https://arxiv.org/abs/2309.11495)) | draft → one `noul` "is the draft correct?" → final with both in the state | BBH `cove` column |
| Few-shot / few-shot CoT ([Brown et al. 2020](https://arxiv.org/abs/2005.14165)) | the official BBH exemplars as structured `instructions`: question → answer, or question → worked solution | BBH `fewshot`, `fewshot-cot` columns |
| Program-aided reasoning ([Gao et al. 2022](https://arxiv.org/abs/2211.10435)) | Jev finds the facts, code applies the rule (`code` strategy: `diverse && amount > 75k`) | LegalBench `code` column |
| Forward chaining (fixed-point iteration) | ask every fact at once and `refine`: a truth value propagates one hop per round (BBH web-of-lies) | BBH `propagate` column |
| Tree of thoughts / beam search | TypeSafe's [hierarchical-classification cookbook](https://docs.typesafe.ai/cookbooks/hierarchical_classification) already does beam search over `choice` probabilities; not duplicated here | — |
| Retrieval augmentation | out of scope; it is the one lever left for knowledge questions like MMLU-Pro | — |

<!-- BBH -->

### LegalBench: rule application on a public benchmark

[LegalBench](https://hazyresearch.stanford.edu/legalbench/) (Guha et al., NeurIPS 2023) has tasks where the answer is a statute applied to facts: *diversity jurisdiction* holds when the parties are completely diverse **and** the amount in controversy exceeds $75,000; *hearsay* is an out-of-court statement **and** offered for its truth; *personal jurisdiction* is domicile **or** (minimum contacts **and** a claim arising from them). The sub-conditions are exactly the intermediate answers a chain needs, and the six diversity variants ship gold labels for both sub-conditions. [`bench/legalbench`](bench/legalbench/run.mjs), all test rows, accuracy with balanced accuracy in parentheses:

| task | n | plain Jev | `refine` | `chain` (sub-conditions → conclusion) | `code` (sub-conditions → rule in code) | GPT-4 · GPT-3.5 · Claude-1 (LegalBench paper, Table 59, correctness) |
| --- | --- | --- | --- | --- | --- | --- |
| diversity_1 | 300 | 100% | 100% | 100% | 100% | — |
| diversity_2 | 300 | 100% | 100% | 100% | 100% | — |
| diversity_3 | 300 | 93.0% (91.5) | 92.7% | 93.7% (92.3) | 93.0% (92.8) | — |
| diversity_4 | 300 | 94.0% (93.6) | 95.0% | 94.3% (93.9) | 93.7% (93.2) | — |
| diversity_5 | 300 | 72.3% (74.5) | 72.0% | **87.3% (86.4)** | **89.7% (88.3)** | 76.6 · 66.7 · 36.7 |
| diversity_6 | 300 | 79.7% (78.4) | 80.7% | **88.7% (87.9)** | **90.3% (89.7)** | 80.0 · 6.7 · 53.3 |
| hearsay | 94 | 78.7% (76.7) | 77.7% | **87.2% (87.3)** | **87.2% (87.6)** | 75.5 · 55.3 · 68.1 |
| personal_jurisdiction | 50 | 86.0% (86.6) | 88.0% | **92.0% (92.4)** | **92.0% (92.4)** | 94.0 · 68.0 · 70.0 |
| calls / item · cost, all 2,144 rows | | 1 · $0.04 | 2 · $0.08 | 2 · $0.09 | 1 · $0.05 | |

Three things to read off this table:

- **The gain is where the structure is.** diversity_1–4 are one plaintiff, one defendant, few claims: plain Jev is at or near ceiling and nothing moves. diversity_5 and 6 add parties and claims that must not be aggregated, and the chain adds 15 and 9 points; hearsay adds 8.5; personal jurisdiction 6. `refine` alone (the draft fed back, no new questions) adds nothing anywhere, the same as on MMLU-Pro: the second call needs new facts in it, not the old answer.
- **Once the facts are typed, code can apply the rule.** `code` asks the same sub-condition questions and applies the statute in JavaScript (`diverse && amount_ok`) for one call. It matches or beats the chain, which is TypeSafe's own recommendation ("code for exact computation, Jev for judgment"). The chain is for rules you cannot or do not want to write as code; the sub-condition table shows both read the facts equally well (diversity_5: parties 86%, amount 98%).
- **Against the LLMs in the LegalBench paper**, Jev with a two-call chain scores above the paper's GPT-4 correctness on diversity_5 (87.3 vs 76.6), diversity_6 (88.7 vs 80.0) and hearsay (87.2 vs 75.5), and below it on personal jurisdiction (92.0 vs 94.0), for about $0.00004 per call. Those are the paper's 2023 measurements (Table 59, "correctness" as judged by the authors, with the paper's prompts), not a fresh run; they are quoted for scale, not as a controlled comparison.


## Reproduce

```bash
git clone https://github.com/leepokai/jev-chain-of-thought && cd jev-chain-of-thought
npm test                                                   # unit tests, no key needed

# data (Python, once): MMLU-Pro from Hugging Face, CLERC slice rebuilt exactly as TypeSafe's cookbook does
python -m venv .venv && .venv/bin/pip install datasets bm25s
.venv/bin/python bench/mmlu-pro/prepare.py bench/data/mmlu_pro.json
.venv/bin/python bench/clerc/prepare.py    bench/data/clerc.json     # prints BM25 top-1/5/10 = 5% / 15% / 38%, matching the cookbook

# benches: every Jev response is cached in bench/results/*.json, so re-running is free and partial runs resume
export JEV_API_KEY=…
node bench/synthetic/run.mjs                 # 100 memos × 5 strategies        ≈ 1,300 calls, $0.04
N=40  node bench/clerc/run.mjs all           # the cookbook's 40 queries        ≈ 4,000 calls, $0.5
N=150 node bench/clerc/run.mjs all           # + the other 110 pooled rows      ≈ 15,000 calls, $2
N=700 node bench/mmlu-pro/run.mjs all        # stratified sample, 7 strategies  ≈ 8,400 calls, $0.3
N=all node bench/mmlu-pro/run.mjs direct     # full test set, 12,032 questions  ≈ $0.3, 9 min at 6 concurrent
```

Each run prints a Markdown table and writes it next to the cache (`bench/results/*.md`). Rate limit is 1,200 requests per minute; the client retries 429/5xx with backoff and honours `retry-after`.

## Design notes

- **Why a second call at all.** Jev packs the state once and scores each question in its own branch; branches do not see each other ([architecture write-up](https://archerhume.com/posts/jevs-architecture-unmasked/), confirmed by TypeSafe's parallel-questions cookbook). Any judgment that is a function of another judgment therefore needs the first answer to be *in the state*. That is the whole trick, and it is why the gain is large on rubrics and zero on atomic questions.
- **Fixed point, not diffusion.** `refine` converges in one round in every benchmark here. It stops as soon as the labels repeat; `rounds` is a cap, not a schedule.
- **The draft is evidence.** Presenting the draft as fallible ("may contain errors: re-check") matters, and even so Jev copies a wrong draft field about a third of the time. Feed back only its own answers to the same document.
- **Cost.** Jev charges input tokens only ($0.042 / M). A feedback pass costs the state again plus a few lines. The expensive design is the cookbook's one-call-per-pair re-ranking; `rerank` sends the query once and the candidates inside isolated questions, which is the same computation for 3% of the calls.
- **Nothing here needs the SDK.** One `fetch` to `POST /v1/systemone`, key from `JEV_API_KEY`, `TYPESAFE_API_KEY` or [`jev-guard key`](https://github.com/leepokai/jev-guard).

## Related

- [jev-guard](https://github.com/leepokai/jev-guard) — the same author's prompt-injection and dangerous-action guard for coding agents, built on Jev.
- [TypeSafe docs](https://docs.typesafe.ai) · [cookbooks](https://docs.typesafe.ai/cookbooks/rerank_typesafe) · [Jev's architecture unmasked](https://archerhume.com/posts/jevs-architecture-unmasked/) · [openjev](https://github.com/TheoLeeCJ/openjev)

MIT © [leepokai](https://github.com/leepokai)

