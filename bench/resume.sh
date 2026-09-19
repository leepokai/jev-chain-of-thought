#!/bin/bash
# Waits until the TypeSafe API accepts calls again (HTTP 402 = no credits), then finishes every technique sweep from the caches
# and re-renders the reports. Each bench is run twice so items that failed transiently on the first pass are retried.
cd "$(dirname "$0")/.." || exit 1
[ -f .env.gateway ] && { set -a; . ./.env.gateway; set +a; }   # optional: VERCEL_OIDC_TOKEN / AI_GATEWAY_API_KEY → route the sweep through Vercel AI Gateway
probe() { node --input-type=module -e 'import { ask } from "./src/jev.js"; try { await ask("ping", { ok: { type: "noul", instructions: "Is this a ping?", criteria: { true: "yes", false: "no" } } }, { model: "jev-1.13.0", retries: 0 }); } catch (e) { console.error(e.message.slice(0, 120)); process.exit(1); }'; }
until probe; do echo "$(date '+%F %T') waiting for credits"; sleep 300; done
echo "$(date '+%F %T') API back, resuming"
for pass in 1 2; do  # the three benches in parallel; the client retries 429s with backoff
  C=14 node bench/bbh/run.mjs all > "bench/results/bbh-sweep-$pass.log" 2>&1 &
  C=8 node bench/legalbench/run.mjs all > "bench/results/legalbench-sweep-$pass.log" 2>&1 &
  N=700 C=8 node bench/mmlu-pro/run.mjs all > "bench/results/mmlu-pro-700-sweep-$pass.log" 2>&1 &
  wait
done
REPORT_ONLY=1 node bench/bbh/run.mjs all > /dev/null 2>&1; REPORT_ONLY=1 node bench/legalbench/run.mjs all > /dev/null 2>&1; REPORT_ONLY=1 N=700 node bench/mmlu-pro/run.mjs all > /dev/null 2>&1
echo "$(date '+%F %T') sweeps done"
