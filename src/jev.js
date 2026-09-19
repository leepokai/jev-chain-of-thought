// Minimal Jev client, two backends: TypeSafe's API (JEV_API_KEY / TYPESAFE_API_KEY, or ~/.jev-guard/config.json written by `jev-guard key`)
// and Vercel AI Gateway (AI_GATEWAY_API_KEY, or VERCEL_OIDC_TOKEN from `vercel env pull`). Env vars win over the config file.
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const URL = "https://api.typesafe.ai/v1/systemone";
export const GATEWAY_URL = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model";

function config() { try { return JSON.parse(readFileSync(join(homedir(), ".jev-guard", "config.json"), "utf8")); } catch { return {}; } }
export function backend(env = process.env) {
  if (env.JEV_API_KEY || env.TYPESAFE_API_KEY) return { kind: "typesafe", key: env.JEV_API_KEY || env.TYPESAFE_API_KEY };
  if (env.AI_GATEWAY_API_KEY) return { kind: "gateway", key: env.AI_GATEWAY_API_KEY, auth: "api-key" };
  if (env.VERCEL_OIDC_TOKEN) return { kind: "gateway", key: env.VERCEL_OIDC_TOKEN, auth: "oidc" };  // expires ~12 h after `vercel env pull`
  const cfg = config();
  if (cfg.jevApiKey) return { kind: "typesafe", key: cfg.jevApiKey };
  if (cfg.aiGatewayApiKey) return { kind: "gateway", key: cfg.aiGatewayApiKey, auth: "api-key" };
  return null;
}
export const apiKey = (env = process.env) => backend(env)?.key;
const mapValues = (o, f) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, f(v, k)]));

/** One call. Returns { answers: {id: {p?, choice?, probabilities?, score?, confidence?}}, usage: {input, output}, model, ms }. */
export async function ask(state, questions, { key, model = "jev-latest", fetchImpl = fetch, retries = 6, timeoutMs = 120_000, env = process.env } = {}) {
  const b = key ? { kind: "typesafe", key } : backend(env);
  if (!b) throw new Error("no credentials: set JEV_API_KEY / TYPESAFE_API_KEY, AI_GATEWAY_API_KEY or VERCEL_OIDC_TOKEN");
  const gw = b.kind === "gateway";
  const q = gw ? mapValues(questions, (x) => (x.type === "noul" ? { ...x, type: "boolean" } : x)) : questions;  // the gateway calls noul "boolean"
  const t0 = performance.now();
  let res;
  for (let attempt = 0; ; attempt++) {
    try {
      res = await fetchImpl(gw ? GATEWAY_URL : URL, {
        method: "POST",
        headers: gw
          ? { Authorization: `Bearer ${b.key}`, "Content-Type": "application/json", "ai-gateway-protocol-version": "0.0.1", "ai-gateway-auth-method": b.auth,
              "ai-evaluation-model-specification-version": "4", "ai-model-id": env.JEV_GATEWAY_MODEL ?? "typesafe-ai/jev" }
          : { Authorization: `Bearer ${b.key}`, "Content-Type": "application/json" },
        body: JSON.stringify(gw ? { state, questions: q, providerOptions: { gateway: { zeroDataRetention: true } } } : { state, model, questions: q }),
        signal: AbortSignal.timeout(timeoutMs) });
      if (res.ok || (res.status !== 429 && res.status !== 529 && res.status < 500) || attempt === retries) break;
      var retryAfter = +res.headers.get("retry-after") * 1000 || 0;  // honour the header when the API sends one
      await res.text().catch(() => {});
    } catch (err) { if (attempt === retries) throw err; }
    await new Promise((r) => setTimeout(r, Math.max(retryAfter, 500 * 2 ** attempt) + Math.random() * 300));
  }
  if (!res.ok) throw new Error(`${gw ? "AI Gateway" : "TypeSafe"} HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const body = await res.json(), conf = body.providerMetadata?.typesafe?.confidence ?? {};
  const answers = mapValues(body.answers, (a, id) => ({
    p: a.noul ?? a.probability, choice: a.choice, probabilities: a.probabilities, score: a.score, confidence: a.confidence ?? conf[id] }));
  return { answers, usage: { input: body.usage?.input_tokens ?? body.usage?.inputTokens ?? 0, output: body.usage?.output_tokens ?? body.usage?.outputTokens ?? 0 },
    model: body.model ?? (gw ? `${env.JEV_GATEWAY_MODEL ?? "typesafe-ai/jev"} via AI Gateway` : model), ms: performance.now() - t0 };
}
