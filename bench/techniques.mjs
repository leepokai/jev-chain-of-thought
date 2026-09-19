// LLM prompting techniques translated for a model that answers typed questions and never generates text.
// Every technique is (state, questions, opts, ctx) → { answers, trace }. ctx supplies exemplars/neighbours where a technique needs them.
import { ask, refine, feedback } from "../src/index.js";

export const one = async (state, qs, opts) => { const r = await ask(state, qs, opts); return { answers: r.answers, trace: [r] }; };
const instr = (q, extra) => ({ ...q, instructions: q.instructions && typeof q.instructions === "object" ? { ...q.instructions, ...extra } : { question: q.instructions, ...extra } });
export const withInstr = (qs, extra) => Object.fromEntries(Object.entries(qs).map(([k, q]) => [k, instr(q, extra)]));
const text = (s) => (typeof s === "string" ? s : JSON.stringify(s));

/** Average several answer sets (choice probabilities or noul p). */
export function average(list) {
  const out = {};
  for (const id of Object.keys(list[0])) {
    const a = list[0][id];
    if (a.probabilities) { const p = Object.fromEntries(Object.keys(a.probabilities).map((k) => [k, list.reduce((s, x) => s + (x[id].probabilities[k] ?? 0), 0) / list.length]));
      out[id] = { choice: Object.keys(p).reduce((m, k) => (p[k] > p[m] ? k : m)), probabilities: p }; }
    else out[id] = { p: list.reduce((s, x) => s + x[id].p, 0) / list.length };
  }
  return out;
}
function rnd(seed) { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
export function shuffled(arr, seed) { const r = rnd(seed), a = [...arr]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
/** Same questions, option order permuted (choice) or criteria swapped (noul). */
export const permuted = (qs, seed) => Object.fromEntries(Object.entries(qs).map(([k, q]) => [k, q.type === "choice"
  ? { ...q, criteria: Object.fromEntries(shuffled(Object.entries(q.criteria), seed)) }
  : q.criteria && seed % 2 ? { ...q, criteria: Object.fromEntries(Object.entries(q.criteria).reverse()) } : q]));

/** Lexical nearest neighbours: token-set Jaccard over a labelled pool (leave-one-out is the caller's job). */
const toks = (s) => new Set(text(s).toLowerCase().match(/[a-z0-9]+/g) ?? []);
export function neighbours(pool, query, k = 5) {
  const q = toks(query);
  return pool.map((it) => { const t = toks(it.question); let inter = 0; for (const w of q) if (t.has(w)) inter++; return [inter / (q.size + t.size - inter || 1), it]; })
    .sort((a, b) => b[0] - a[0]).slice(0, k).map(([, it]) => it);
}

const FRAMINGS = ["Decide strictly from the evidence given.", "Consider each option in turn before choosing.", "First rule out what is clearly wrong, then choose among what remains."];

export const TECHNIQUES = {
  // baseline
  direct: (s, qs, o) => one(s, qs, o),
  // zero-shot phrasing tricks: role, emotion, "let's think step by step", re-reading
  role: (s, qs, o, ctx) => one(s, withInstr(qs, { role: ctx?.role ?? "You are a meticulous expert in this domain; answer as the expert would." }), o),
  emotion: (s, qs, o) => one(s, withInstr(qs, { note: "This is very important to my career. Take a deep breath and be careful: a wrong answer has real consequences." }), o),
  "zs-cot": (s, qs, o) => one(s, withInstr(qs, { hint: "Let's think step by step before deciding." }), o),
  reread: (s, qs, o) => one(typeof s === "string" ? `${s}\n\nRead the question again:\n${s}` : { ...s, read_again: text(s) }, qs, o),
  // ensembles: instruction framings averaged; option orders averaged
  "prompt-ensemble": async (s, qs, o) => { const rs = await Promise.all(FRAMINGS.map((f) => ask(s, withInstr(qs, { approach: f }), o))); return { answers: average(rs.map((r) => r.answers)), trace: rs }; },
  permute: async (s, qs, o) => { const n = Object.values(qs).some((q) => q.type === "choice") ? 3 : 2; const rs = await Promise.all(Array.from({ length: n }, (_, i) => ask(s, i ? permuted(qs, i) : qs, o))); return { answers: average(rs.map((r) => r.answers)), trace: rs }; },
  // in-context examples: fixed, with worked solutions, retrieved by similarity, contrastive (a wrong answer shown alongside)
  fewshot: (s, qs, o, ctx) => one(s, withInstr(qs, { examples: ctx.exemplars.map(({ question, answer }) => ({ question, answer })) }), o),
  "fewshot-cot": (s, qs, o, ctx) => one(s, withInstr(qs, { examples: ctx.exemplars.map(({ question, worked_solution }) => ({ question, worked_solution })) }), o),
  knn: (s, qs, o, ctx) => one(s, withInstr(qs, { similar_solved_examples: ctx.neighbours.map(({ question, answer }) => ({ question, answer })) }), o),
  contrastive: (s, qs, o, ctx) => one(s, withInstr(qs, { examples: ctx.exemplars.map(({ question, answer, wrong }) => ({ question, correct_answer: answer, incorrect_answer: wrong })) }), o),
  // second passes: self-refine, chain-of-verification
  refine: (s, qs, o) => refine(s, qs, { rounds: 1, ...o }),
  cove: async (s, qs, o) => {
    const d = await ask(s, qs, o);
    const v = await ask(feedback(s, d.answers), { draft_correct: { type: "noul", instructions: "Is the draft answer correct? Check it against the evidence step by step.", criteria: { true: "The draft answer is correct.", false: "The draft answer is wrong." } } }, o);
    const f = await ask(feedback(s, { ...d.answers, draft_check: v.answers.draft_correct }), qs, o);
    return { answers: f.answers, trace: [d, v, f] };
  },
};
export const SINGLE_CALL = ["direct", "role", "emotion", "zs-cot", "reread", "fewshot", "fewshot-cot", "knn", "contrastive"];
/** Offline majority vote over single-call techniques (ties → first listed). */
export function vote(choices) { const c = {}; for (const x of choices) if (x != null) c[x] = (c[x] ?? 0) + 1; return Object.keys(c).sort((a, b) => c[b] - c[a] || choices.indexOf(a) - choices.indexOf(b))[0]; }
