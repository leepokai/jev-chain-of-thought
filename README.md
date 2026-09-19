# jev-chain-of-thought

**Chain-of-thought and self-refinement for [TypeSafe's Jev](https://typesafe.ai). Feed Jev's typed answers back as state and ask again.**

Jev is a *System One* model: it never generates text, it answers typed questions (`choice`, `noul`, `score`) about a `state` and returns calibrated probabilities. That makes it 100× cheaper than an LLM judge, but it also means it has no scratchpad. Every question in a request is scored on its own; a question cannot see what Jev answered to the question next to it, and Jev cannot revise an answer after seeing its own first draft.

This package adds the scratchpad in code: ask Jev, render its answers as text, put that text back into the state, ask again. Three primitives, zero dependencies, one fetch:

| primitive | what it does | when it helps |
| --- | --- | --- |
| `refine(state, questions)` | ask, feed the draft back, ask again until the labels stop changing | rubrics where one answer depends on another |
| `chain(state, [steps…, final])` | each step's answers become established facts for the next step | decompose a judgment into the facts it depends on |
| `choose(state, options)` / `rerank(query, candidates)` | ready-made chains for multiple choice and for ranking | MMLU-style questions, retrieval re-ranking |

<!-- RESULTS -->

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

<!-- BENCH -->
