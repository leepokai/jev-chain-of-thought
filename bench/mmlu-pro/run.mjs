// MMLU-Pro (TIGER-Lab, 12,032 ten-option questions) with plain Jev vs jev-chain-of-thought strategies.
// usage: N=420 node bench/mmlu-pro/run.mjs [strategy,...|all]     N = size of a seeded stratified sample (N=all for the full test set)
import { readFileSync, writeFileSync } from "node:fs";
import { choose, pmap, top } from "../../src/index.js";
import { cache, shuffle, table, pct, PRICE } from "../lib.mjs";
import { TECHNIQUES, SINGLE_CALL, neighbours, vote } from "../techniques.mjs";
const val = JSON.parse(readFileSync(new URL("../data/mmlu_pro_val.json", import.meta.url)));  // 5 CoT exemplars per category

const MODEL = process.env.MODEL ?? "jev-1.13.0", C = +(process.env.C || 12), N = process.env.N ?? "420";
const all = JSON.parse(readFileSync(new URL("../data/mmlu_pro.json", import.meta.url)));
// stratified sample: seeded shuffle, then round-robin over categories so every subset size keeps the category mix
const byCat = {}; for (const q of shuffle(all, 0)) (byCat[q.category] ??= []).push(q);
const order = []; for (let i = 0; order.length < all.length; i++) for (const c of Object.keys(byCat).sort()) if (byCat[c][i]) order.push(byCat[c][i]);
const Q = N === "all" ? order : order.slice(0, +N);

const STRATEGIES = {
  direct: { strategy: "direct" },                       // 1 call: one choice over the options
  refine: { strategy: "refine" },                       // 2 calls: choice, then choice again with its own draft (control: no new information)
  permute: { strategy: "permute", permutations: 3 },    // 3 calls: option order shuffled, probabilities averaged (control: order bias only)
  verify: { strategy: "verify" },                       // 2 calls: choice + one "is this option correct?" noul per option, then choice with that draft
  narrow: { strategy: "narrow", k: 3 },                 // 2 calls: choice, then choice over the top 3 with the draft
  cot: { strategy: "cot", k: 3 },                       // 2 calls: verify's first call, then narrow's second
  product: { strategy: "product" },                     // 1 call: listwise choice × per-option nouls, multiplied (ensemble of two views, no feedback)
};
const letters = "ABCDEFGHIJ";
const fmt = (q, options) => `${q}\nOptions:\n${options.map((o, i) => `(${letters[i]}) ${o}`).join("\n")}`;
const ctxFor = (q) => ({ exemplars: val.filter((v) => v.category === q.category).map((v, i) => ({ question: fmt(v.q, v.options), answer: v.answer, worked_solution: v.cot.replace(/^A:\s*/, ""), wrong: letters[(letters.indexOf(v.answer) + 1 + i) % v.options.length] })),
  neighbours: neighbours(byCat[q.category].filter((x) => x.id !== q.id).map((x) => ({ question: fmt(x.q, x.options), answer: x.answer })), q.q, 5), role: `You are a meticulous expert in ${q.category}; answer as the expert would.` });
for (const [name, fn] of Object.entries(TECHNIQUES)) STRATEGIES[name] ??= { technique: fn };
const want = process.argv[2] && process.argv[2] !== "all" ? process.argv[2].split(",") : Object.keys(STRATEGIES);
const { c: R, save } = cache(new URL("../results/mmlu-pro.json", import.meta.url));
const options = (q) => Object.fromEntries(q.options.map((o, i) => [letters[i], o]));

for (const name of want) {
  R[name] ??= {};
  const todo = Q.filter((q) => !R[name][q.id]);
  if (todo.length && !process.env.REPORT_ONLY) {  // REPORT_ONLY=1 renders whatever is cached without calling the API
    const t0 = performance.now(); let n = 0;
    let failed = 0;
    await pmap(todo, async (q) => {
      let r; try { r = STRATEGIES[name].technique
        ? await STRATEGIES[name].technique({ question: q.q, subject: q.category }, { answer: { type: "choice", instructions: "Which option correctly answers the question?", criteria: options(q) } }, { model: MODEL }, ctxFor(q)).then((x) => ({ choice: x.answers.answer.choice, probabilities: x.answers.answer.probabilities, trace: x.trace, calls: x.trace.length }))
        : await choose({ question: q.q, subject: q.category }, options(q), { ...STRATEGIES[name], instructions: "Which option correctly answers the question?", model: MODEL }); }
      catch (e) { failed++; if (failed < 5) console.error(`\n${q.id}: ${e.message}`); return; }
      const a0 = r.trace[0].answers, first = a0[`A_correct`] ? { list: a0.answer.probabilities, noul: Object.fromEntries(Object.keys(options(q)).map((o) => [o, a0[`${o}_correct`].p])) } : undefined;
      R[name][q.id] = { choice: r.choice, p: +r.probabilities[r.choice].toFixed(4), calls: r.calls, first, input: r.trace.reduce((s, t) => s + t.usage.input, 0), ms: r.trace.reduce((s, t) => s + t.ms, 0) };
      if (++n % 200 === 0) { save(); process.stdout.write(`${n} `); }
    }, C);
    console.log(` ${name}: ${todo.length} questions, ${((performance.now() - t0) / 1000).toFixed(0)}s wall${failed ? `, ${failed} failed (rerun to retry)` : ""}`);
    save();
  }
}

const cats = Object.keys(byCat).sort(), rows = [], perCat = [];
for (const name of [...Object.keys(STRATEGIES), "vote"]) {
  if (name === "vote") R.vote = Object.fromEntries(Q.map((q) => { const cs = SINGLE_CALL.map((n) => R[n]?.[q.id]?.choice); return cs.filter(Boolean).length >= 3 ? [q.id, { choice: vote(cs), p: 0, calls: 0, input: 0, ms: 0 }] : [q.id, null]; }));
  if (!Q.every((q) => R[name]?.[q.id])) continue;
  const rs = Q.map((q) => ({ ...R[name][q.id], ok: R[name][q.id].choice === q.answer, cat: q.category }));
  const acc = rs.filter((r) => r.ok).length / rs.length;
  const bins = Array.from({ length: 10 }, () => ({ n: 0, p: 0, ok: 0 }));
  for (const r of rs) { const b = bins[Math.min(9, Math.floor(r.p * 10))]; b.n++; b.p += r.p; b.ok += r.ok; }
  const ece = bins.reduce((s, b) => s + (b.n ? (b.n / rs.length) * Math.abs(b.ok / b.n - b.p / b.n) : 0), 0);
  const tok = rs.reduce((s, r) => s + r.input, 0);
  rows.push({ strategy: name, accuracy: pct(acc), "mean top-p": (rs.reduce((s, r) => s + r.p, 0) / rs.length).toFixed(3), ECE: ece.toFixed(3),
    "calls/q": (rs.reduce((s, r) => s + r.calls, 0) / rs.length).toFixed(2), "tokens/q": Math.round(tok / rs.length), cost: `$${(tok * PRICE).toFixed(2)}`, "s/q": (rs.reduce((s, r) => s + r.ms, 0) / rs.length / 1000).toFixed(2) });
  perCat.push({ strategy: name, ...Object.fromEntries(cats.map((c) => { const x = rs.filter((r) => r.cat === c); return [c, x.length ? pct(x.filter((r) => r.ok).length / x.length) : "-"]; })) });
}
const withFirst = Object.keys(STRATEGIES).find((n) => Q.every((q) => R[n]?.[q.id]?.first));
if (withFirst) {  // offline: other ways to combine the listwise and per-option views, no extra calls
  const combos = { "nouls only (argmax p)": (f) => f.noul, "mean of views": (f) => Object.fromEntries(Object.keys(f.list).map((o) => [o, (f.list[o] + f.noul[o]) / 2])) };
  for (const [name, fn] of Object.entries(combos)) {
    const ok = Q.filter((q) => { const p = fn(R[withFirst][q.id].first); return Object.keys(p).reduce((a, b) => (p[b] > p[a] ? b : a)) === q.answer; }).length;
    rows.push({ strategy: `${name} (offline, from ${withFirst})`, accuracy: pct(ok / Q.length), "mean top-p": "", ECE: "", "calls/q": "", "tokens/q": "", cost: "", "s/q": "" });
  }
}
const md = `# MMLU-Pro (${Q.length} questions${N === "all" ? ", full test set" : ", stratified sample"}, model ${MODEL})\n\n${table(rows)}\n\nPer category:\n\n${table(perCat)}\n`;
console.log("\n" + md);
writeFileSync(new URL(`../results/mmlu-pro-${N}.md`, import.meta.url), md);
