// Synthetic rubric benchmark: 100 OCR-noised transaction memos, three rubric questions that depend on each other
// (requires_review depends on risk_level). Shows why feeding answers back helps: questions in one Jev call cannot see each other's answers.
// usage: node bench/synthetic/run.mjs        (generator: github.com/leepokai/claude-daily-tasks experiments/jev/jev.py make_doc)
import { readFileSync, writeFileSync } from "node:fs";
import { ask, refine, chain, choose, pmap, label, top } from "../../src/index.js";
import { cache, table, pct, PRICE } from "../lib.mjs";

const MODEL = process.env.MODEL ?? "jev-1.13.0", C = +(process.env.C || 8);
const memos = JSON.parse(readFileSync(new URL("./memos.json", import.meta.url)));
const RULES = `
Risk score = amount points + origin points + note points.
Amount: >= 50,000 -> 2; 10,000-49,999 -> 1; < 10,000 -> 0.
Origin in {Cayman Islands, Panama, Iran, Belize} -> +2, else 0.
Notes: sanctions screening / fraud pattern / structuring or laundering -> +3; dispute, chargeback, first-time counterparty -> +1; routine invoice -> 0; verified recurring vendor, verified payroll, internal transfer between own accounts -> -1.
The text is OCR output and may contain character substitutions (O/0, l/1, S/5, dropped spaces).`;
const FINAL = {
  risk_level: { type: "choice", instructions: `Risk level of this transaction.${RULES}`, criteria: { HIGH: "score >= 4", MEDIUM: "score 2-3", LOW: "score 1", NONE: "score <= 0" } },
  requires_review: { type: "noul", instructions: `Does this need manual review? True when risk level is HIGH or MEDIUM, or the notes mention a dispute.${RULES}`,
    criteria: { true: "Risk is HIGH or MEDIUM, or the notes mention a dispute.", false: "Risk is LOW or NONE and the notes do not mention a dispute." } },
  action_tier: { type: "choice", instructions: `Action tier for this transaction.${RULES}`, criteria: { TIER_1: "risk HIGH or amount >= 50,000", TIER_2: "otherwise, risk MEDIUM or amount >= 10,000", TIER_3: "everything else" } },
};
const STEPS = {  // the rubric's three inputs, asked first
  amount_bucket: { type: "choice", instructions: "Which bracket is the USD Amount in? The text is OCR output (O/0, l/1, S/5 substitutions, dropped spaces).", criteria: { large: ">= 50,000", mid: "10,000 to 49,999", small: "< 10,000" } },
  origin_high_risk: { type: "noul", instructions: "Is the Origin country one of: Cayman Islands, Panama, Iran, Belize? OCR noise possible.", criteria: { true: "Origin is Cayman Islands, Panama, Iran or Belize.", false: "Origin is any other country." } },
  note_kind: { type: "choice", instructions: "Which category do the Notes fall in?", criteria: { severe: "sanctions screening, fraud pattern, structuring or laundering", minor: "dispute, chargeback, or first-time counterparty", routine: "routine invoice settlement", trusted: "verified recurring vendor, verified payroll, or internal transfer between own accounts" } },
};
const STRATEGIES = {
  direct: (doc) => refine(doc, FINAL, { rounds: 0, model: MODEL }),
  refine: (doc) => refine(doc, FINAL, { rounds: 3, model: MODEL }),
  chain: (doc) => chain(doc, [STEPS, FINAL], { model: MODEL }),
  "chain+refine": (doc) => chain(doc, [STEPS, FINAL], { refine: 3, model: MODEL }),
};
const { c: R, save } = cache(new URL("../results/synthetic.json", import.meta.url));
for (const [name, run] of Object.entries(STRATEGIES)) {
  if (R[name]?.length === memos.length) continue;
  const t0 = performance.now();
  R[name] = await pmap(memos, async ({ doc }) => { const r = await run(doc); return { pred: Object.fromEntries(Object.keys(FINAL).map((f) => [f, label(r.answers[f])])), conf: Object.keys(FINAL).reduce((s, f) => s + top(r.answers[f]), 0) / 3, calls: r.calls, input: r.usage.input, ms: r.trace.reduce((s, t) => s + t.ms, 0) }; }, C);
  console.log(`${name}: ${((performance.now() - t0) / 1000).toFixed(0)}s wall`); save();
}
const fields = Object.keys(FINAL), rows = [];
for (const name of Object.keys(STRATEGIES)) {
  const rs = R[name]; if (!rs) continue;
  const acc = (f) => rs.filter((r, i) => r.pred[f] === memos[i].gold[f]).length / rs.length;
  rows.push({ strategy: name, ...Object.fromEntries(fields.map((f) => [f, pct(acc(f))])), "all 3": pct(rs.filter((r, i) => fields.every((f) => r.pred[f] === memos[i].gold[f])).length / rs.length),
    "mean top-p": (rs.reduce((s, r) => s + r.conf, 0) / rs.length).toFixed(2), "calls/doc": (rs.reduce((s, r) => s + r.calls, 0) / rs.length).toFixed(2), cost: `$${(rs.reduce((s, r) => s + r.input, 0) * PRICE).toFixed(4)}`, "s/doc": (rs.reduce((s, r) => s + r.ms, 0) / rs.length / 1000).toFixed(2) });
}
const md = `# Synthetic rubric memos (${memos.length} docs, model ${MODEL})\n\n${table(rows)}\n`;
console.log("\n" + md); writeFileSync(new URL("../results/synthetic.md", import.meta.url), md);
