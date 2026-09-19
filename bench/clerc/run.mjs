// Replicates TypeSafe's re-ranking cookbook (docs.typesafe.ai/cookbooks/rerank_typesafe: 40 CLERC queries × 30 BM25 candidates,
// one noul per pair, jev-1.12 → top-1 18%, top-5 35%, top-10 62%) and adds jev-chain-of-thought strategies on the identical slice.
// usage: node bench/clerc/run.mjs [strategy,...|all]    data: bench/clerc/prepare.py → bench/data/clerc.json
import { readFileSync, writeFileSync } from "node:fs";
import { rerank, pmap } from "../../src/index.js";
import { cache, table, pct, PRICE } from "../lib.mjs";

const MODEL = process.env.MODEL ?? "jev-1.13.0", N = +(process.env.N || 40), C = +(process.env.C || 8);
const { queries, corpus } = JSON.parse(readFileSync(new URL("../data/clerc.json", import.meta.url)));
const Q = N <= 40 ? queries.filter((q) => q.cookbook).slice(0, N) : queries.slice(0, N);  // 40 = the cookbook's queries; 150 = every pooled row
// verbatim from the cookbook
const instructions = "The query excerpt comes from a US federal court opinion and was written immediately around a citation to a precedent; the citation itself has been removed. Could the candidate passage be from that cited precedent — does it establish the specific legal proposition the query excerpt invokes at its citation point?";
const criteria = {
  true: "The candidate passage states or establishes the specific rule, standard, holding, or fact pattern that the query excerpt attributes to its removed citation.",
  false: "The candidate passage is merely on a similar topic or doctrine; it does not supply the specific proposition the query excerpt relies on.",
};
// chain-of-thought facets: decompose the judgment into three cheaper sub-judgments and average them (log-odds) with the main question
const facets = {
  same_rule: { instructions: "Does the candidate passage state the same legal rule, standard or holding that the query excerpt relies on at its citation point (not merely the same area of law)?",
    criteria: { true: "The same specific rule, standard or holding.", false: "A different rule, or only the same general doctrine." } },
  citable_language: { instructions: "Does the query excerpt quote, paraphrase or closely track language that appears in the candidate passage?",
    criteria: { true: "Wording in the query excerpt tracks the candidate's language.", false: "No shared or paraphrased wording." } },
  fact_pattern: { instructions: "Is the candidate passage the kind of authoritative statement (a court's holding or rule) that the query excerpt would cite, rather than a recitation of facts, procedure or a party's argument?",
    criteria: { true: "An authoritative holding or rule statement.", false: "Facts, procedural history, or a party's argument." } },
};
const STRATEGIES = {
  pointwise: { strategy: "pointwise" },                                  // cookbook replica: 30 calls per query
  fanout: { strategy: "fanout" },                                        // 1 call per query: 30 isolated nouls, query shared
  listwise: { strategy: "listwise" },                                    // 1 call per query: one choice over 30 ids
  cot: { strategy: "cot", topK: 10 },                                    // pointwise, then listwise over the top 10 with the draft
  "cot-fanout": { strategy: "cot", pointwise: "fanout", topK: 10 },      // same, 2 calls per query
  cot5: { strategy: "cot", topK: 5, reuse: "pointwise" },                // listwise over the top 5 only (pointwise scores reused from the run above)
  cot30: { strategy: "cot", topK: 30, reuse: "pointwise" },              // listwise over all 30, with every pointwise score as draft
  facets: { strategy: "pointwise", facets },                             // 30 calls per query, 4 nouls each, composite score
  "facets-cot": { strategy: "cot", facets, topK: 10, reuse: "facets" },  // composite pointwise, then listwise over the top 10
};
const want = process.argv[2] && process.argv[2] !== "all" ? process.argv[2].split(",") : Object.keys(STRATEGIES);
const { c: R, save } = cache(new URL("../results/clerc.json", import.meta.url));  // keyed by strategy then qid, so N=40 and N=150 share calls

for (const name of want) {
  R[name] ??= {};
  const todo = Q.filter((q) => !R[name][q.qid]);
  if (todo.length) {
    const t0 = performance.now();
    let failed = 0;
    await pmap(todo, async (q) => {
      try {
      const cands = Object.fromEntries(q.candidates.map((c) => [c, corpus[c]]));
      const { reuse, ...opts } = STRATEGIES[name];
      const prev = reuse && R[reuse]?.[q.qid];
      const r = await rerank(q.query, cands, { ...opts, scores: prev?.scores, instructions, criteria, queryKey: "query_excerpt", candidateKey: "candidate_passage", model: MODEL, concurrency: 8 });
      R[name][q.qid] = { ranking: r.ranking, scores: r.scores, calls: r.calls + (prev?.calls ?? 0), input: r.trace.reduce((s, t) => s + t.usage.input, 0) + (prev?.input ?? 0), ms: r.trace.reduce((s, t) => s + t.ms, 0) + (prev?.ms ?? 0), model: r.trace[0].model };
      process.stdout.write(".");
      } catch (e) { failed++; console.error(`\n${q.qid}: ${e.message}`); }
    }, STRATEGIES[name].pointwise === "fanout" || STRATEGIES[name].strategy === "listwise" ? C : 2);
    console.log(` ${name}: ${((performance.now() - t0) / 1000).toFixed(0)}s wall${failed ? `, ${failed} failed (rerun to retry)` : ""}`);
    save();
  }
}

const rows = [];
const metrics = (name, rankOf) => {
  const ranks = Q.map((q) => rankOf(q));
  const at = (n) => ranks.filter((r) => r <= n).length / ranks.length;
  return { strategy: name, "top-1": pct(at(1)), "top-5": pct(at(5)), "top-10": pct(at(10)), MRR: (ranks.reduce((s, r) => s + 1 / r, 0) / ranks.length).toFixed(3) };
};
rows.push({ ...metrics("BM25 only (cookbook: 5% / 15% / 38%)", (q) => q.candidates.indexOf(q.gold) + 1), calls: 0, "input tokens": 0, cost: "$0", "s/query": "-" });
for (const name of Object.keys(STRATEGIES)) {
  if (!Q.every((q) => R[name]?.[q.qid])) continue;
  const rs = Q.map((q) => R[name][q.qid]);
  const tok = rs.reduce((s, r) => s + r.input, 0);
  rows.push({ ...metrics(name + (name === "pointwise" ? " (cookbook replica: 18% / 35% / 62%)" : ""), (q) => R[name][q.qid].ranking.indexOf(q.gold) + 1),
    calls: rs.reduce((s, r) => s + r.calls, 0), "input tokens": tok.toLocaleString(), cost: `$${(tok * PRICE).toFixed(4)}`, "s/query": (rs.reduce((s, r) => s + r.ms, 0) / rs.length / 1000).toFixed(1) });
}
if (Q.every((q) => R.pointwise?.[q.qid] && R.listwise?.[q.qid])) {  // offline: multiply pointwise and listwise probabilities, no extra calls
  rows.push({ ...metrics("pointwise × listwise (offline)", (q) => { const p = R.pointwise[q.qid].scores, l = R.listwise[q.qid].scores; return [...q.candidates].sort((a, b) => p[b] * l[b] - p[a] * l[a]).indexOf(q.gold) + 1; }), calls: "", "input tokens": "", cost: "", "s/query": "" });
}
// paired bootstrap over queries: is each strategy's MRR really different from the cookbook replica's?
const boot = [];
if (Q.every((q) => R.pointwise?.[q.qid])) {
  const rr = (name, q) => 1 / (R[name][q.qid].ranking.indexOf(q.gold) + 1);
  let seed = 1; const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x80000000; };
  for (const name of Object.keys(STRATEGIES).filter((n) => n !== "pointwise" && Q.every((q) => R[n]?.[q.qid]))) {
    const d = Q.map((q) => rr(name, q) - rr("pointwise", q)), B = 4000, means = [];
    for (let b = 0; b < B; b++) { let s = 0; for (let i = 0; i < d.length; i++) s += d[Math.floor(rnd() * d.length)]; means.push(s / d.length); }
    means.sort((a, b) => a - b);
    const mean = d.reduce((s, x) => s + x, 0) / d.length, lo = means[Math.floor(B * 0.025)], hi = means[Math.floor(B * 0.975)];
    boot.push({ strategy: name, "ΔMRR vs pointwise": (mean >= 0 ? "+" : "") + mean.toFixed(3), "95% CI": `[${lo.toFixed(3)}, ${hi.toFixed(3)}]`, "calls vs pointwise": `${(R[name][Q[0].qid].calls / R.pointwise[Q[0].qid].calls * 100).toFixed(0)}%`, "P(Δ ≤ 0)": (means.filter((m) => m <= 0).length / B).toFixed(3) });
  }
}
const md = `# CLERC re-ranking (${Q.length} queries × 30 BM25 candidates, model ${MODEL})\n\n${table(rows)}\n${boot.length ? `\nPaired bootstrap (${Q.length} queries, 4,000 resamples), reciprocal rank of the gold passage per query:\n\n${table(boot)}\n` : ""}`;
console.log("\n" + md);
writeFileSync(new URL(`../results/clerc-${N}.md`, import.meta.url), md);
