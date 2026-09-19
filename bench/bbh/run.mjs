// BIG-Bench Hard with Jev: the benchmark that made chain-of-thought famous (Suzgun et al. 2022), 23 tasks with option answers.
// Generic strategies on every task (direct, few-shot, few-shot with the official CoT exemplars, self-refine, chain-of-verification)
// and typed chains built from the task structure for the four families where intermediate answers exist.
// usage: TASKS=web_of_lies,navigate N=50 node bench/bbh/run.mjs [strategy,...|all]     data: bench/bbh/prepare.py → bench/data/bbh.json
import { readFileSync, writeFileSync } from "node:fs";
import { ask, refine, feedback, pmap } from "../../src/index.js";
import { cache, table, pct, PRICE } from "../lib.mjs";
import { TECHNIQUES, SINGLE_CALL, neighbours, vote } from "../techniques.mjs";

const MODEL = process.env.MODEL ?? "jev-1.13.0", C = +(process.env.C || 12), N = process.env.N ? +process.env.N : Infinity;
const data = JSON.parse(readFileSync(new URL("../data/bbh.json", import.meta.url)));
const TASKS = process.env.TASKS ? process.env.TASKS.split(",") : Object.keys(data);
const opts = { model: MODEL };

function parse(task, ex) {
  const m = ex.input.match(/\nOptions:\n([\s\S]*)$/);
  if (m) {
    const options = {};
    for (const line of m[1].trim().split("\n")) { const o = line.match(/^\(([A-Z])\)\s*(.*)$/); if (o) options[o[1]] = o[2].trim(); else { const y = line.match(/^-\s*(.*)$/); if (y) options[y[1]] = y[1]; } }
    return { text: ex.input.slice(0, m.index).trim(), options, gold: ex.target.match(/^\(([A-Z])\)$/)?.[1] ?? ex.target };
  }
  return { text: ex.input.trim(), options: Object.fromEntries(data[task].targets.map((t) => [t, t])), gold: ex.target };
}
// the official prompt file: a one-line task description, then three worked examples ending in "So the answer is X."
function official(task) {
  const body = data[task].cot_prompt.split("-----\n")[1] ?? data[task].cot_prompt;
  const [desc, ...qs] = body.split(/\n\nQ: /);
  const examples = qs.map((q) => { const [question, ...rest] = q.split("\nA: "); const a = rest.join("\nA: ").trim();
    return { question: question.trim(), reasoning: a, answer: (a.match(/So the answer is (.*?)\.?\s*$/s)?.[1] ?? "").trim() }; });
  return { desc: desc.trim(), examples };
}
const Q = (p, extra = {}) => ({ answer: { type: "choice", instructions: { task: official_desc, question: "Which option is correct?", ...extra }, criteria: p.options } });
let official_desc = "";

// every generic technique sees the same state/questions; exemplars come from the official prompt file, neighbours from the task's other items
const wrongFor = (question, answer) => { const letters = [...question.matchAll(/^\(([A-Z])\)/gm)].map((m) => `(${m[1]})`).filter((l) => l !== answer);
  return letters.length ? letters[0] : ({ Yes: "No", No: "Yes", yes: "no", no: "yes", True: "False", False: "True", valid: "invalid", invalid: "valid" })[answer] ?? "(none of the above)"; };
const one = async (state, qs) => { const r = await ask(state, qs, opts); return { answers: r.answers, trace: [r] }; };
let pool = [];  // the current task's items, for knn (leave-one-out)
const ctxFor = (p, task) => { const ex = official(task).examples.map((e) => ({ question: e.question, answer: e.answer, worked_solution: e.reasoning, wrong: wrongFor(e.question, e.answer) }));
  return { exemplars: ex, neighbours: neighbours(pool.filter((x) => x !== p).map((x) => ({ question: x.text, answer: x.gold })), p.text, 5) }; };
const GENERIC = Object.fromEntries(Object.entries(TECHNIQUES).map(([name, fn]) => [name, (p, task) => fn({ question: p.text }, Q(p), opts, ctxFor(p, task))]));
const noul = (question, extra = {}) => ({ type: "noul", instructions: { question, ...extra }, criteria: { true: "Yes.", false: "No." } });
const sentences = (t) => t.split(/(?<=[.?!])\s+/);
const CHAINS = {
  // progressive state: after each swap, ask what every person holds; the previous step's holdings are established facts
  tracking: async (p) => {
    const s = sentences(p.text), swaps = s.map((x, i) => (/swap|trade|switch/i.test(x) ? i : -1)).filter((i) => i >= 0);
    const people = s[0].split(/ (?:are|is|were) /)[0].split(/,\s*(?:and\s+)?|\s+and\s+/).map((x) => x.trim()).filter(Boolean);
    const trace = []; let facts;
    for (const k of swaps) {
      let state = { events_so_far: s.slice(0, k + 1).join(" ") };
      if (facts) state = feedback(state, facts, "facts");
      const r = await ask(state, Object.fromEntries(people.map((P) => [`${P}_has`, { type: "choice", instructions: { question: `After the events so far, which option is ${P} currently with?`, hint: "Apply only the last swap to the established facts." }, criteria: p.options }])), opts);
      trace.push(r); facts = r.answers;
    }
    const f = await ask(feedback({ question: p.text }, facts, "facts"), Q(p), opts); trace.push(f);
    return { answers: f.answers, trace };
  },
  // one person per step, in the order the statements appear; each depends on the previous person's truthfulness
  lies: async (p) => {
    const names = sentences(p.text.replace(/^Question:\s*/, "")).map((x) => x.match(/^(\w+)\s+(?:tells|says)/)?.[1]).filter(Boolean);
    const trace = []; let facts = {};
    for (const n of names) {
      const r = await ask(feedback({ question: p.text }, facts, "facts"), { [`${n}_tells_truth`]: noul(`Does ${n} tell the truth?`, { rule: "A truthful person's statement about someone is accurate; a liar's statement is the opposite of the truth." }) }, opts);
      trace.push(r); facts = { ...facts, ...r.answers };
    }
    const f = await ask(feedback({ question: p.text }, facts, "facts"), Q(p), opts); trace.push(f);
    return { answers: f.answers, trace };
  },
  // everyone at once, then iterate: truth propagates one hop per round (fixed-point iteration)
  propagate: async (p) => {
    const names = sentences(p.text.replace(/^Question:\s*/, "")).map((x) => x.match(/^(\w+)\s+(?:tells|says)/)?.[1]).filter(Boolean);
    const qs = Object.fromEntries(names.map((n) => [`${n}_tells_truth`, noul(`Does ${n} tell the truth?`, { rule: "A truthful person's statement about someone is accurate; a liar's statement is the opposite of the truth." })]));
    const r = await refine({ question: p.text }, qs, { rounds: names.length, ...opts });
    const f = await ask(feedback({ question: p.text }, r.answers, "facts"), Q(p), opts);
    return { answers: f.answers, trace: [...r.trace, f] };
  },
  // assign every object a position, let the assignments see each other for two rounds, then answer
  deduction: async (p) => {
    const m = p.text.match(/there are \w+ [\w\s-]+?: (.*?)\./i); if (!m) return GENERIC.direct(p);
    const objects = m[1].split(/,\s*(?:and\s+)?|\s+and\s+/).map((x) => x.replace(/^(a|an|the)\s+/, "").trim()).filter(Boolean), n = objects.length;
    const pos = Object.fromEntries(Array.from({ length: n }, (_, i) => [String(i + 1), `position ${i + 1} of ${n}, counting from the first-mentioned end of the order (leftmost, oldest, cheapest, first…) toward the other end`]));
    const qs = Object.fromEntries(objects.map((o) => [`${o.replace(/\s+/g, "_")}_position`, { type: "choice", instructions: { question: `Which position does the ${o} occupy?`, rule: "Every object has a different position; all statements are consistent." }, criteria: pos }]));
    const r = await refine({ paragraph: p.text }, qs, { rounds: 2, ...opts });
    const f = await ask(feedback({ question: p.text }, r.answers, "facts"), Q(p), opts);
    return { answers: f.answers, trace: [...r.trace, f] };
  },
  // one noul per candidate slot, then the choice with those facts
  temporal: async (p) => {
    const name = p.text.match(/Today, (\w+) went/)?.[1] ?? "the person";
    const qs = Object.fromEntries(Object.entries(p.options).map(([k, slot]) => [`slot_${k}_possible`, noul(`Could ${name} have gone there during ${slot}: not seen anywhere else during that time, and the place open?`)]));
    const r = await ask({ question: p.text }, qs, opts);
    const f = await ask(feedback({ question: p.text }, r.answers, "facts"), Q(p), opts);
    return { answers: f.answers, trace: [r, f] };
  },
};
CHAINS.structured = async (p) => {  // chain-of-symbol / structured input: the same question over a parsed JSON state instead of prose
  const s = sentences(p.text.replace(/^Question:\s*/, ""));
  const state = /swap|trade|switch/i.test(p.text) ? { setup: s.filter((x) => !/swap|trade|switch/i.test(x) && x !== s.at(-1)).join(" "), swaps_in_order: s.filter((x) => /swap|trade|switch/i.test(x)), question: s.at(-1) }
    : { statements_in_order: s.slice(0, -1), question: s.at(-1) };
  return one(state, Q(p));
};
const CHAIN_FOR = (task) => task.startsWith("tracking") ? ["tracking", "structured"] : task === "web_of_lies" ? ["lies", "propagate", "structured"] : task.startsWith("logical_deduction") ? ["deduction"] : task === "temporal_sequences" ? ["temporal"] : [];
const want = process.argv[2] && process.argv[2] !== "all" ? process.argv[2].split(",") : [...Object.keys(GENERIC), ...Object.keys(CHAINS)];
const { c: R, save } = cache(new URL("../results/bbh.json", import.meta.url));

for (const task of TASKS) {
  official_desc = official(task).desc;
  const items = data[task].examples.map((ex) => parse(task, ex)).filter((p) => p.gold in p.options).slice(0, N); pool = items;
  R[task] ??= {};
  for (const name of want.filter((n) => GENERIC[n] || CHAIN_FOR(task).includes(n))) {
    R[task][name] ??= {};
    const todo = items.map((p, i) => [p, i]).filter(([, i]) => !R[task][name][i]);
    if (!todo.length || process.env.REPORT_ONLY) continue;  // REPORT_ONLY=1 renders whatever is cached without calling the API
    const t0 = performance.now(); let failed = 0;
    await pmap(todo, async ([p, i]) => {
      try { const r = await (GENERIC[name] ?? CHAINS[name])(p, task);
        R[task][name][i] = { choice: r.answers.answer.choice, calls: r.trace.length, input: r.trace.reduce((s, t) => s + t.usage.input, 0) }; }
      catch (e) { failed++; if (failed < 3) console.error(`\n${task}/${name}/${i}: ${e.message}`); }
    }, C);
    console.log(`${task} ${name}: ${todo.length} items, ${((performance.now() - t0) / 1000).toFixed(0)}s${failed ? `, ${failed} failed` : ""}`); save();
  }
}

// report: tasks × strategies
const names = [...Object.keys(GENERIC), "vote", ...Object.keys(CHAINS)], rows = [], sums = {};
for (const task of TASKS) {
  const items = data[task].examples.map((ex) => parse(task, ex)).filter((p) => p.gold in p.options).slice(0, N);
  const row = { task, n: items.length };
  for (const name of names) {
    const rs = name === "vote" ? Object.fromEntries(items.map((_, i) => { const cs = SINGLE_CALL.map((n) => R[task]?.[n]?.[i]?.choice); return cs.filter(Boolean).length >= 3 ? [i, { choice: vote(cs), calls: 0, input: 0 }] : [i, null]; })) : R[task]?.[name];
    if (!rs || items.some((_, i) => !rs[i])) { row[name] = ""; continue; }
    const acc = items.filter((p, i) => rs[i].choice === p.gold).length / items.length;
    row[name] = pct(acc); (sums[name] ??= { acc: 0, n: 0, calls: 0, tok: 0, tasks: 0 });  // only complete columns are reported (sums[name] ??= { acc: 0, n: 0, calls: 0, tok: 0, tasks: 0 });
    sums[name].acc += acc; sums[name].tasks++; sums[name].calls += items.reduce((s, _, i) => s + rs[i].calls, 0); sums[name].tok += items.reduce((s, _, i) => s + rs[i].input, 0); sums[name].n += items.length;
  }
  rows.push(row);
}
rows.push({ task: "**mean over tasks**", n: "", ...Object.fromEntries(names.map((n) => [n, sums[n] ? `${pct(sums[n].acc / sums[n].tasks)} (${sums[n].tasks})` : ""])) });
rows.push({ task: "calls / item", n: "", ...Object.fromEntries(names.map((n) => [n, sums[n] ? (sums[n].calls / sums[n].n).toFixed(2) : ""])) });
rows.push({ task: "cost", n: "", ...Object.fromEntries(names.map((n) => [n, sums[n] ? `$${(sums[n].tok * PRICE).toFixed(2)}` : ""])) });
const md = `# BIG-Bench Hard (${TASKS.length} tasks, model ${MODEL})\n\n${table(rows)}\n`;
console.log("\n" + md); if (!process.env.N && !process.env.TASKS) writeFileSync(new URL("../results/bbh.md", import.meta.url), md);
