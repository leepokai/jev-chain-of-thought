// Minimal TypeSafe client. Reads JEV_API_KEY / TYPESAFE_API_KEY, or ~/.jev-guard/config.json written by `jev-guard key`.
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const URL = "https://api.typesafe.ai/v1/systemone";

export function apiKey(env = process.env) {
  if (env.JEV_API_KEY || env.TYPESAFE_API_KEY) return env.JEV_API_KEY || env.TYPESAFE_API_KEY;
  try { return JSON.parse(readFileSync(join(homedir(), ".jev-guard", "config.json"), "utf8")).jevApiKey; } catch { return undefined; }
}

/** One call. Returns { answers: {id: {p?, choice?, probabilities?, score?, confidence?}}, usage: {input, output}, model, ms }. */
export async function ask(state, questions, { key = apiKey(), model = "jev-latest", fetchImpl = fetch, retries = 6, timeoutMs = 120_000 } = {}) {
  if (!key) throw new Error("no API key: set JEV_API_KEY (or TYPESAFE_API_KEY)");
  const t0 = performance.now();
  let res;
  for (let attempt = 0; ; attempt++) {
    try {
      res = await fetchImpl(URL, { method: "POST", headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
        body: JSON.stringify({ state, model, questions }), signal: AbortSignal.timeout(timeoutMs) });
      if (res.ok || (res.status !== 429 && res.status !== 529 && res.status < 500) || attempt === retries) break;
      var retryAfter = +res.headers.get("retry-after") * 1000 || 0;  // honour the header when the API sends one
      await res.text().catch(() => {});
    } catch (err) { if (attempt === retries) throw err; }
    await new Promise((r) => setTimeout(r, Math.max(retryAfter, 500 * 2 ** attempt) + Math.random() * 300));
  }
  if (!res.ok) throw new Error(`TypeSafe HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const body = await res.json();
  const answers = Object.fromEntries(Object.entries(body.answers).map(([id, a]) => [id, {
    p: a.noul, choice: a.choice, probabilities: a.probabilities, score: a.score, confidence: a.confidence }]));
  return { answers, usage: { input: body.usage?.input_tokens ?? 0, output: body.usage?.output_tokens ?? 0 }, model: body.model, ms: performance.now() - t0 };
}
