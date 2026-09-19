// shared bench helpers: disk cache per strategy, seeded shuffle, markdown tables
import { readFileSync, writeFileSync, existsSync } from "node:fs";
export const PRICE = 0.042 / 1e6;  // $ per input token, jev-1.13 (output tokens are free)
export function cache(file) {
  const c = existsSync(file) ? JSON.parse(readFileSync(file)) : {};
  return { c, save: () => writeFileSync(file, JSON.stringify(c)) };
}
export function shuffle(items, seed = 0) {
  let a = seed >>> 0; const rnd = () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const ks = [...items]; for (let i = ks.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [ks[i], ks[j]] = [ks[j], ks[i]]; } return ks;
}
export const table = (rows) => { const h = Object.keys(rows[0]); return [h.join(" | "), h.map(() => "---").join(" | "), ...rows.map((r) => h.map((k) => r[k]).join(" | "))].map((l) => `| ${l} |`).join("\n"); };
export const pct = (x) => `${(100 * x).toFixed(1)}%`;
