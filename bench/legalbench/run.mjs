// LegalBench (Guha et al. 2023) rule-application tasks: the answer is a conjunction of sub-conditions the statute names.
// direct = ask the conclusion; chain = ask the sub-conditions, then the conclusion with them as facts; code = ask the sub-conditions and let code apply the rule.
// usage: node bench/legalbench/run.mjs [strategy,...|all]     data: bench/legalbench/prepare.py → bench/data/legalbench.json
import { readFileSync, writeFileSync } from "node:fs";
import { ask, refine, chain, pmap, label } from "../../src/index.js";
import { cache, table, pct, PRICE } from "../lib.mjs";

const MODEL = process.env.MODEL ?? "jev-1.13.0", C = +(process.env.C || 12), N = process.env.N ? +process.env.N : Infinity;
const data = JSON.parse(readFileSync(new URL("../data/legalbench.json", import.meta.url)));
const opts = { model: MODEL };
const noul = (question, extra = {}) => ({ type: "noul", instructions: { question, ...extra }, criteria: { true: "Yes.", false: "No." } });

// rules as LegalBench states them in each task's README
const RULES = {
  diversity: {
    rule: "A federal court has diversity jurisdiction over a claim when (1) the parties are completely diverse: no plaintiff is a citizen of the same state as any defendant, and (2) the amount in controversy exceeds $75,000. A single plaintiff may aggregate all of their claims against a single defendant to reach the threshold; claims by different plaintiffs, or against different defendants, are not aggregated.",
    steps: { parties_are_diverse: noul("Are the parties completely diverse: does no plaintiff share a state of citizenship with any defendant?"),
             aic_is_met: noul("Is the amount-in-controversy requirement met: does some plaintiff's total claims against some defendant exceed $75,000?", { note: "Aggregate only one plaintiff's claims against one defendant. Exactly $75,000 does not exceed $75,000." }) },
    final: noul("Is there diversity jurisdiction over this case?"),
    code: (a) => a.parties_are_diverse && a.aic_is_met,
  },
  hearsay: {
    rule: "Hearsay is (1) an out-of-court statement, made by a person, (2) offered in court to prove the truth of the matter asserted in the statement. Non-assertive conduct, statements not offered for their truth (e.g. to show effect on the listener, or that words were spoken), and statements made in the present court proceeding are not hearsay.",
    steps: { out_of_court_statement: noul("Is the evidence a statement (an assertion, oral, written or by assertive conduct) that was made outside the current court proceeding?"),
             offered_for_truth: noul("Is the statement being offered to prove that what it asserts is true, rather than for some other purpose (effect on the listener, that the words were said, state of mind)?") },
    final: noul("Is this evidence hearsay?"),
    code: (a) => a.out_of_court_statement && a.offered_for_truth,
  },
  personal_jurisdiction: {
    rule: "A court in a forum state has personal jurisdiction over a defendant when (1) the defendant is domiciled in the forum state (general jurisdiction), or (2) the defendant has sufficient minimum contacts with the forum state AND the plaintiff's claim arises out of or relates to those contacts (specific jurisdiction).",
    steps: { domiciled_in_forum: noul("Is the defendant domiciled in (lives in) the state where the suit is brought?"),
             has_contacts: noul("Does the defendant have purposeful minimum contacts with the forum state, such as doing business, travelling there for work, or directing conduct at it?"),
             claim_arises_from_contacts: noul("Does the plaintiff's claim arise out of or relate to the defendant's contacts with the forum state?") },
    final: noul("Does the court have personal jurisdiction over the defendant?"),
    code: (a) => a.domiciled_in_forum || (a.has_contacts && a.claim_arises_from_contacts),
  },
};
const ruleFor = (task) => RULES[task.replace(/_\d$/, "")];
const withRule = (q, rule) => ({ ...q, instructions: { ...q.instructions, rule } });

const STRATEGIES = {
  direct: async (task, text) => { const { rule, final } = ruleFor(task); return refine({ facts: text }, { answer: withRule(final, rule) }, { rounds: 0, ...opts }); },
  refine: async (task, text) => { const { rule, final } = ruleFor(task); return refine({ facts: text }, { answer: withRule(final, rule) }, { rounds: 1, ...opts }); },
  chain: async (task, text) => { const { rule, final, steps } = ruleFor(task);
    return chain({ facts: text }, [Object.fromEntries(Object.entries(steps).map(([k, q]) => [k, withRule(q, rule)])), { answer: withRule(final, rule) }], opts); },
  code: async (task, text) => { const { rule, steps, code } = ruleFor(task);  // program-of-thought: Jev finds the facts, code applies the rule
    const r = await ask({ facts: text }, Object.fromEntries(Object.entries(steps).map(([k, q]) => [k, withRule(q, rule)])), opts);
    const a = Object.fromEntries(Object.keys(steps).map((k) => [k, r.answers[k].p >= 0.5]));
    return { answers: { ...r.answers, answer: { p: code(a) ? 1 : 0 } }, trace: [r], calls: 1, usage: r.usage }; },
};
const want = process.argv[2] && process.argv[2] !== "all" ? process.argv[2].split(",") : Object.keys(STRATEGIES);
const { c: R, save } = cache(new URL("../results/legalbench.json", import.meta.url));

for (const task of Object.keys(data)) {
  const items = data[task].slice(0, N); R[task] ??= {};
  for (const name of want) {
    R[task][name] ??= {};
    const todo = items.map((it, i) => [it, i]).filter(([, i]) => !R[task][name][i]);
    if (!todo.length) continue;
    const t0 = performance.now(); let failed = 0;
    await pmap(todo, async ([it, i]) => {
      try { const r = await STRATEGIES[name](task, it.text), all = { ...(r.trace[0]?.answers ?? {}), ...r.answers };  // chain: sub-conditions live in the first pass
        R[task][name][i] = { answer: r.answers.answer.p >= 0.5 ? "Yes" : "No", steps: Object.fromEntries(Object.keys(ruleFor(task).steps).filter((k) => all[k]).map((k) => [k, all[k].p >= 0.5])), calls: r.trace.length, input: r.trace.reduce((s, t) => s + t.usage.input, 0) }; }
      catch (e) { failed++; if (failed < 3) console.error(`\n${task}/${name}/${i}: ${e.message}`); }
    }, C);
    console.log(`${task} ${name}: ${todo.length} items, ${((performance.now() - t0) / 1000).toFixed(0)}s${failed ? `, ${failed} failed` : ""}`); save();
  }
}

const rows = [], sub = [];
for (const task of Object.keys(data)) {
  const items = data[task].slice(0, N), row = { task, n: items.length };
  for (const name of Object.keys(STRATEGIES)) {
    const rs = R[task]?.[name]; if (!rs || items.some((_, i) => !rs[i])) { row[name] = ""; continue; }
    row[name] = pct(items.filter((it, i) => rs[i].answer === it.answer).length / items.length);
  }
  rows.push(row);
  if ("parties_are_diverse" in items[0]) for (const name of ["chain", "code"]) {  // diversity ships gold for both sub-conditions
    const rs = R[task]?.[name]; if (!rs || items.some((_, i) => !rs[i])) continue;
    sub.push({ task, strategy: name, parties_are_diverse: pct(items.filter((it, i) => rs[i].steps.parties_are_diverse === it.parties_are_diverse).length / items.length),
      aic_is_met: pct(items.filter((it, i) => rs[i].steps.aic_is_met === it.aic_is_met).length / items.length), "both sub-conditions": pct(items.filter((it, i) => rs[i].steps.parties_are_diverse === it.parties_are_diverse && rs[i].steps.aic_is_met === it.aic_is_met).length / items.length) });
  }
}
const calls = Object.fromEntries(Object.keys(STRATEGIES).map((n) => { const all = Object.keys(data).flatMap((t) => Object.values(R[t]?.[n] ?? {})); return [n, all.length ? `${(all.reduce((s, r) => s + r.calls, 0) / all.length).toFixed(2)} calls, $${(all.reduce((s, r) => s + r.input, 0) * PRICE).toFixed(2)}` : ""]; }));
rows.push({ task: "calls / item, cost", n: "", ...calls });
const md = `# LegalBench rule-application tasks (model ${MODEL})\n\n${table(rows)}\n${sub.length ? `\nSub-condition accuracy on the diversity tasks (gold shipped with the dataset):\n\n${table(sub)}\n` : ""}`;
console.log("\n" + md); if (!process.env.N) writeFileSync(new URL("../results/legalbench.md", import.meta.url), md);
