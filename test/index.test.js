import { test } from "node:test";
import assert from "node:assert/strict";
import { render, feedback, refine, chain, choose, rerank, same } from "../src/index.js";

// fake Jev: answers every question from a lookup, records the states it saw
const fake = (table) => { const seen = []; const ask = async (state, qs) => { seen.push({ state, qs }); return { answers: Object.fromEntries(Object.keys(qs).map((id) => [id, table(id, qs[id], state)])), usage: { input: 1, output: 0 } }; }; ask.seen = seen; return ask; };

test("render and feedback", () => {
  const a = { risk: { choice: "HIGH", probabilities: { HIGH: 0.9, LOW: 0.1 } }, review: { p: 0.3 }, sev: { score: 2.5 } };
  assert.equal(render(a), "risk: HIGH (HIGH 0.90, LOW 0.10)\nreview: false (p=0.30)\nsev: 2.50");
  assert.match(feedback("doc", a), /^doc\n\n--- Draft .*\nrisk: HIGH/);
  const o = feedback(feedback({ doc: 1 }, a, "facts"), a, "facts");
  assert.equal(o.established_facts.answers.split("risk: HIGH").length, 3);  // facts accumulate
  assert.equal(feedback(feedback({ doc: 1 }, a), a).draft_answers.answers, render(a));  // drafts replace
});

test("refine stops at the fixed point", async () => {
  let n = 0;
  const ask = fake(() => ({ p: n++ < 1 ? 0.2 : 0.8 }));  // first pass false, then true, true
  const r = await refine("doc", { q: { type: "noul", instructions: "?" } }, { rounds: 5, ask });
  assert.equal(r.calls, 3); assert.equal(r.answers.q.p, 0.8); assert.equal(r.usage.input, 3);
  assert.ok(same(r.trace[1].answers, r.trace[2].answers));
});

test("chain feeds facts forward", async () => {
  const ask = fake((id) => (id === "fact" ? { choice: "x", probabilities: { x: 1 } } : { p: 0.9 }));
  const r = await chain("doc", [{ fact: { type: "choice" } }, { final: { type: "noul" } }], { ask });
  assert.equal(r.calls, 2); assert.match(ask.seen[1].state, /fact: x/);
});

test("choose narrows to top-k and renormalises", async () => {
  const ask = fake((id, q) => id === "answer" ? (Object.keys(q.criteria).length === 4
    ? { choice: "A", probabilities: { A: 0.4, B: 0.3, C: 0.2, D: 0.1 } } : { choice: "B", probabilities: { A: 0.2, B: 0.6, C: 0.2 } }) : { p: 0.5 });
  const r = await choose("q", { A: "a", B: "b", C: "c", D: "d" }, { strategy: "cot", k: 3, ask });
  assert.equal(r.choice, "B"); assert.equal(r.calls, 2);
  assert.ok(Math.abs(Object.values(r.probabilities).reduce((s, x) => s + x) - 1) < 1e-9);
  assert.equal(Object.keys(ask.seen[0].qs).length, 5);  // listwise + 4 verify nouls in one call
  assert.match(ask.seen[1].state, /A_correct: true/);
});

test("rerank cot: pointwise then listwise over the head", async () => {
  const ask = fake((id, q, state) => id === "best" ? { choice: "c2", probabilities: { c1: 0.1, c2: 0.9 } } : { p: state.candidate === "one" ? 0.9 : state.candidate === "two" ? 0.8 : 0.1 });
  const r = await rerank("q", { c1: "one", c2: "two", c3: "three" }, { instructions: "?", topK: 2, pointwise: "pointwise", ask });
  assert.deepEqual(r.ranking, ["c2", "c1", "c3"]); assert.equal(r.calls, 4);
  const f = fake((id, q) => id === "best" ? { choice: "c1", probabilities: { c1: 0.6, c2: 0.4 } } : { p: q.instructions.candidate === "two" ? 0.9 : 0.5 });
  const r2 = await rerank("q", { c1: "one", c2: "two", c3: "three" }, { instructions: "?", topK: 2, ask: f });  // default: fanout + listwise = 2 calls
  assert.deepEqual(r2.ranking, ["c1", "c2", "c3"]); assert.equal(r2.calls, 2);
});
