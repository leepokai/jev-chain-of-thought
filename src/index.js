// jev-chain-of-thought: Jev answers typed questions but never sees its own answers. Feed them back as state and ask again.
import { ask as jevAsk } from "./jev.js";
export { jevAsk as ask };

const DRAFT = "Draft answers from a previous pass. They may contain errors: re-check each one against the evidence and correct it.";
const FACTS = "Answers established in a previous pass.";

export const label = (a) => a.choice ?? (a.score !== undefined ? a.score.toFixed(1) : String(a.p >= 0.5));
export const top = (a) => a.probabilities && a.choice !== undefined ? a.probabilities[a.choice] : a.score !== undefined ? (a.confidence ?? 1) : Math.max(a.p, 1 - a.p);

/** Answers as text the model can read back: `id: label (option prob, ...)`. */
export function render(answers) {
  return Object.entries(answers).map(([id, a]) => {
    if (a.probabilities && a.choice !== undefined) return `${id}: ${a.choice} (${Object.entries(a.probabilities).sort((x, y) => y[1] - x[1]).map(([k, v]) => `${k} ${v.toFixed(2)}`).join(", ")})`;
    if (a.score !== undefined) return `${id}: ${a.score.toFixed(2)}`;
    return `${id}: ${a.p >= 0.5} (p=${a.p.toFixed(2)})`;
  }).join("\n");
}

/** Attach answers to a state (string, array or object). kind "draft" replaces an earlier draft; "facts" accumulate. */
export function feedback(state, answers, kind = "draft") {
  const note = kind === "draft" ? DRAFT : FACTS, text = render(answers);
  if (typeof state === "string") return `${state}\n\n--- ${note} ---\n${text}`;
  if (Array.isArray(state)) return [...state, `--- ${note} ---\n${text}`];
  if (kind === "draft") return { ...state, draft_answers: { note, answers: text } };
  return { ...state, established_facts: { note, answers: [state.established_facts?.answers, text].filter(Boolean).join("\n") } };
}

export const same = (a, b) => Object.keys(a).every((id) => b[id] && label(a[id]) === label(b[id]));
const done = (trace) => ({ answers: trace.at(-1).answers, trace, calls: trace.length,
  usage: trace.reduce((s, t) => ({ input: s.input + (t.usage?.input ?? 0), output: s.output + (t.usage?.output ?? 0) }), { input: 0, output: 0 }) });

/** Ask, feed the answers back, ask again; stop when the labels stop changing or after `rounds` extra passes. */
export async function refine(state, questions, { rounds = 2, first, ask = jevAsk, ...opts } = {}) {
  const trace = [first ?? await ask(state, questions, opts)];
  for (let i = 0; i < rounds; i++) {
    trace.push(await ask(feedback(state, trace.at(-1).answers), questions, opts));
    if (same(trace.at(-1).answers, trace.at(-2).answers)) break;
  }
  return done(trace);
}

/** Chain of thought: each step's answers become established facts for the next step. `refine` adds self-refine passes on the last step. */
export async function chain(state, steps, { refine: rounds = 0, ask = jevAsk, ...opts } = {}) {
  const trace = []; let s = state;
  for (const [i, qs] of steps.entries()) {
    const r = await ask(s, qs, opts); trace.push(r);
    if (i < steps.length - 1) s = feedback(s, r.answers, "facts");
  }
  if (!rounds) return done(trace);
  const r = await refine(s, steps.at(-1), { rounds, first: trace.at(-1), ask, ...opts });
  return done([...trace.slice(0, -1), ...r.trace]);
}

/** Multiple choice over options {key: text}. strategy: direct | refine | permute | verify | narrow | cot (verify + narrow) | product (one call: listwise × per-option nouls, no feedback). */
export async function choose(state, options, { instructions = "Which option is correct?", strategy = "cot", k = 3, permutations = 3, id = "answer", ask = jevAsk, ...opts } = {}) {
  const keys = Object.keys(options), trace = [];
  const choice = (ks) => ({ [id]: { type: "choice", instructions, criteria: Object.fromEntries(ks.map((o) => [o, options[o]])) } });
  const verify = Object.fromEntries(keys.map((o) => [`${o}_correct`, { type: "noul",
    instructions: { question: "Is this option the correct answer?", option: o, text: options[o] },
    criteria: { true: "This option is the correct answer.", false: "This option is not the correct answer." } }]));
  const call = async (s, qs) => { const r = await ask(s, qs, opts); trace.push(r); return r.answers; };
  let probs;
  if (strategy === "permute") {
    const runs = await Promise.all(Array.from({ length: permutations }, (_, i) => call(state, choice(i ? shuffle(keys, i) : keys))));
    probs = Object.fromEntries(keys.map((o) => [o, runs.reduce((s, a) => s + a[id].probabilities[o], 0) / runs.length]));
  } else {
    const withVerify = strategy === "verify" || strategy === "cot" || strategy === "product";
    const first = await call(state, withVerify ? { ...choice(keys), ...verify } : choice(keys));
    probs = first[id].probabilities;
    if (strategy === "product") {
      const raw = keys.map((o) => probs[o] * first[`${o}_correct`].p), z = raw.reduce((s, x) => s + x, 0) || 1;
      probs = Object.fromEntries(keys.map((o, i) => [o, raw[i] / z]));
    } else if (strategy !== "direct") {
      const ks = strategy === "narrow" || strategy === "cot" ? [...keys].sort((a, b) => probs[b] - probs[a]).slice(0, k) : keys;
      const p2 = (await call(feedback(state, first), choice(ks)))[id].probabilities;
      const mass = ks.reduce((s, o) => s + probs[o], 0);
      probs = Object.fromEntries(keys.map((o) => [o, ks.includes(o) ? p2[o] * mass : probs[o]]));
    }
  }
  const best = keys.reduce((a, b) => (probs[b] > probs[a] ? b : a));
  return { choice: best, probabilities: probs, trace, calls: trace.length };
}

/** Rank candidates {id: text} for a query. strategy: pointwise | fanout | listwise | cot (pointwise, then listwise over the top `topK` with the draft).
 *  `facets`: extra noul questions {name: {instructions, criteria}} asked about every pair and averaged in log-odds with the main one (composite scoring).
 *  `scores`: precomputed pointwise scores {id: p} to skip the pointwise pass. */
export async function rerank(query, candidates, { instructions, criteria = { true: "Relevant.", false: "Not relevant." }, strategy = "cot", topK = 10, concurrency = 8,
  queryKey = "query", candidateKey = "candidate", pointwise = "pointwise", facets = {}, scores: precomputed, ask = jevAsk, ...opts } = {}) {
  if (!instructions) throw new Error("rerank needs `instructions`: what makes a candidate the right one for the query");
  const ids = Object.keys(candidates), trace = [], scores = {};
  const call = async (s, qs) => { const r = await ask(s, qs, opts); trace.push(r); return r.answers; };
  const qs = { relevant: { instructions, criteria }, ...facets };
  const logit = (p) => Math.log(Math.min(Math.max(p, 1e-4), 1 - 1e-4) / (1 - Math.min(Math.max(p, 1e-4), 1 - 1e-4)));
  const combine = (ps) => 1 / (1 + Math.exp(-ps.reduce((s, p) => s + logit(p), 0) / ps.length));  // mean log-odds → probability-like score
  const scorePointwise = async () => {
    if (precomputed) return Object.assign(scores, precomputed);  // reuse pointwise scores from an earlier pass
    if (pointwise === "fanout") {  // one call: the query is the state, each candidate travels inside its own (isolated) questions
      const a = await call({ [queryKey]: query }, Object.fromEntries(ids.flatMap((c) => Object.entries(qs).map(([f, q]) => [`${c}__${f}`, { type: "noul", instructions: { question: q.instructions, [candidateKey]: candidates[c] }, criteria: q.criteria }]))));
      for (const c of ids) scores[c] = combine(Object.keys(qs).map((f) => a[`${c}__${f}`].p));
    } else await pmap(ids, async (c) => {
      const a = await call({ [queryKey]: query, [candidateKey]: candidates[c] }, Object.fromEntries(Object.entries(qs).map(([f, q]) => [f, { type: "noul", ...q }])));
      scores[c] = combine(Object.keys(qs).map((f) => a[f].p));
    }, concurrency);
  };
  const listwise = async (ks, state) => (await call(state, { best: { type: "choice", instructions: { question: instructions, pick: "The id of the single best candidate." },
    criteria: Object.fromEntries(ks.map((c) => [c, `candidate ${c}`])) } })).best.probabilities;
  const byScore = (ks, s) => [...ks].sort((a, b) => s[b] - s[a]);
  const out = (ranking, s = scores) => ({ ranking, scores: s, trace, calls: trace.length });
  if (strategy === "pointwise" || strategy === "fanout") { if (strategy === "fanout") pointwise = "fanout"; await scorePointwise(); return out(byScore(ids, scores)); }
  if (strategy === "listwise") { const p = await listwise(ids, { [queryKey]: query, candidates }); return out(byScore(ids, p), p); }
  await scorePointwise();
  const head = byScore(ids, scores).slice(0, topK);
  const draft = Object.fromEntries(head.map((c) => [`${c}_relevant`, { p: scores[c] }]));
  const p = await listwise(head, feedback({ [queryKey]: query, candidates: Object.fromEntries(head.map((c) => [c, candidates[c]])) }, draft));
  return out([...byScore(head, p), ...byScore(ids, scores).slice(topK)], { ...scores, ...Object.fromEntries(head.map((c) => [c, 1 + p[c]])) });
}

/** Run fn over items with at most n in flight. */
export async function pmap(items, fn, n = 8) {
  const out = new Array(items.length); let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => { for (let k; (k = i++) < items.length;) out[k] = await fn(items[k], k); }));
  return out;
}

function shuffle(keys, seed) {  // deterministic permutation per seed (mulberry32)
  let a = seed >>> 0; const rnd = () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const ks = [...keys]; for (let i = ks.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [ks[i], ks[j]] = [ks[j], ks[i]]; } return ks;
}
