"""JevLM: a DSPy language model backed by TypeSafe's Jev (direct API or Vercel AI Gateway).

Jev never generates text. The adapter (dspy_jev.adapter.JevAdapter) serialises a DSPy signature into Jev's typed
questions and puts that JSON in the single user message; this LM sends it and returns the answers as JSON text.
"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any

import dspy
import requests

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
GATEWAY_URL = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"


def _config() -> dict:
    try:
        return json.loads((Path.home() / ".jev-guard" / "config.json").read_text())
    except OSError:
        return {}


def backend(env: dict | None = None, prefer: str | None = None) -> dict:
    """Pick credentials: env vars first, then ~/.jev-guard/config.json. `prefer` forces 'typesafe' or 'gateway'."""
    env = os.environ if env is None else env
    cfg = _config()
    candidates = [
        ("typesafe", env.get("JEV_API_KEY") or env.get("TYPESAFE_API_KEY"), None),
        ("gateway", env.get("AI_GATEWAY_API_KEY"), "api-key"),
        ("gateway", env.get("VERCEL_OIDC_TOKEN"), "oidc"),  # from `vercel env pull`, expires ~12 h
        ("typesafe", cfg.get("jevApiKey"), None),
        ("gateway", cfg.get("aiGatewayApiKey"), "api-key"),
    ]
    for kind, key, auth in candidates:
        if key and (prefer is None or prefer == kind):
            return {"kind": kind, "key": key, "auth": auth}
    raise RuntimeError("no Jev credentials: set JEV_API_KEY / TYPESAFE_API_KEY, AI_GATEWAY_API_KEY or VERCEL_OIDC_TOKEN")


class JevLM(dspy.BaseLM):
    """`dspy.BaseLM` for Jev. Use with `dspy.configure(lm=JevLM(), adapter=JevAdapter())`.

    Args:
        model: TypeSafe model id for the direct API (`jev-latest`, `jev-1.13.0`).
        backend: force "typesafe" or "gateway"; default picks from the environment.
        gateway_model: model id on Vercel AI Gateway.
        cache: use `dspy.cache` (memory + disk) keyed on the exact payload.
    """

    forward_contract = "typed_lm"

    def __init__(self, model: str = "jev-latest", backend: str | None = None, gateway_model: str = "typesafe-ai/jev",
                 timeout: float = 120.0, max_retries: int = 6, cache: bool = True, session: requests.Session | None = None, **kwargs):
        super().__init__(model=model, cache=cache, **kwargs)
        self.backend_name = backend
        self.gateway_model = gateway_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._backend: dict | None = None

    # --- transport -------------------------------------------------------------------------------------------------
    def _resolve(self) -> dict:
        if self._backend is None:
            self._backend = backend(prefer=self.backend_name)
        return self._backend

    def _post(self, state: Any, questions: dict) -> dict:
        b = self._resolve()
        gw = b["kind"] == "gateway"
        q = {k: ({**v, "type": "boolean"} if v.get("type") == "noul" else v) for k, v in questions.items()} if gw else questions
        if gw:
            url, headers = GATEWAY_URL, {"Authorization": f"Bearer {b['key']}", "ai-gateway-protocol-version": "0.0.1",
                                         "ai-gateway-auth-method": b["auth"], "ai-evaluation-model-specification-version": "4",
                                         "ai-model-id": self.gateway_model}
            body = {"state": state, "questions": q, "providerOptions": {"gateway": {"zeroDataRetention": True}}}
        else:
            url, headers = TYPESAFE_URL, {"Authorization": f"Bearer {b['key']}"}
            body = {"state": state, "model": self.model, "questions": q}
        for attempt in range(self.max_retries + 1):
            try:
                res = self.session.post(url, json=body, headers=headers, timeout=self.timeout)
            except requests.RequestException:
                if attempt == self.max_retries:
                    raise
                res = None
            if res is not None and (res.ok or (res.status_code not in (429, 529) and res.status_code < 500) or attempt == self.max_retries):
                break
            wait = float(res.headers.get("retry-after", 0)) if res is not None else 0
            time.sleep(max(wait, 0.5 * 2**attempt) + random.random() * 0.3)
        if not res.ok:
            raise RuntimeError(f"{'AI Gateway' if gw else 'TypeSafe'} HTTP {res.status_code}: {res.text[:300]}")
        data = res.json()
        conf = (data.get("providerMetadata") or {}).get("typesafe", {}).get("confidence", {})
        answers = {}
        for qid, a in data["answers"].items():
            out = {}
            if "noul" in a or "probability" in a:
                out["p"] = a.get("noul", a.get("probability"))
            if "choice" in a:
                out["choice"], out["probabilities"] = a["choice"], a.get("probabilities")
            if "score" in a:
                out["score"] = a["score"]
            if a.get("confidence", conf.get(qid)) is not None:
                out["confidence"] = a.get("confidence", conf.get(qid))
            answers[qid] = out
        usage = data.get("usage") or {}
        return {"answers": answers, "usage": {"prompt_tokens": usage.get("input_tokens", usage.get("inputTokens", 0)),
                                              "completion_tokens": usage.get("output_tokens", usage.get("outputTokens", 0))},
                "model": data.get("model") or (f"{self.gateway_model} via AI Gateway" if gw else self.model)}

    # --- DSPy contract ---------------------------------------------------------------------------------------------
    def forward(self, request: dspy.LMRequest) -> dspy.LMResponse:
        text = next((p.text for m in reversed(request.messages) for p in m.parts if getattr(p, "type", None) == "text"), None)
        if text is None:
            raise ValueError("JevLM expects a JSON payload from JevAdapter in the last message")
        payload = json.loads(text)
        key = {"jev": payload, "backend": self._resolve()["kind"], "model": self.model}
        cached = dspy.cache.get(key) if self.cache else None
        if cached is None:
            cached = self._post(payload["state"], payload["questions"])
            if self.cache:
                dspy.cache.put(key, cached)
            hit = False
        else:
            hit = True
        return dspy.LMResponse.from_text(json.dumps(cached["answers"]), model=cached["model"], usage=cached["usage"], cache_hit=hit)
