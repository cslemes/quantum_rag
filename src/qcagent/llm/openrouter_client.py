"""Fronteira B client — a second model family through OpenRouter (research.md D10).

OpenRouter speaks the OpenAI chat-completions protocol, so this is plain
`httpx` against `/chat/completions` (the `openai` SDK is not a dependency).

Three things are pinned here that would otherwise be hidden variables of the
kind F15 found in `temperature`:

- the UPSTREAM PROVIDER. OpenRouter may route one model id to different
  hosts (OpenAI, Azure, Bedrock for gpt-6-luna). The request names one and
  forbids fallbacks, and the provider that actually served each call is
  counted, so a silent reroute would show in the record;
- reasoning EFFORT, stated rather than left to the provider default;
- the reasoning HEADROOM: reasoning tokens share the completion budget, and
  the nodes size `max_tokens` for a non-reasoning model's visible output
  (critic 512), so a fixed headroom is added on top — the same fix the
  Anthropic client needed.
"""

import re
import time
from typing import Final

import httpx

from qcagent.llm.base import BaseLLMClient, LLMResponse, TransientProviderError

DEFAULT_BASE_URL: Final = "https://openrouter.ai/api/v1"

# USD per million tokens (input, output), OpenRouter list prices read from
# /api/v1/models on 2026-09-26. The measured cost OpenRouter reports per call
# (`usage.cost`) is preferred when present; this table is the fallback and
# the pre-run estimate.
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "openai/gpt-6-luna": (0.10, 0.50),
    "openai/gpt-6-sol-pro": (2.00, 10.00),
}

# The standard (non-flex, non-fast) endpoint of the model's own vendor.
_PINNED_PROVIDER: dict[str, str] = {
    "openai/gpt-6-luna": "openai",
    "openai/gpt-6-sol-pro": "openai",
}

REASONING_HEADROOM_TOKENS: Final = 12_000
EFFORT: Final = "high"

_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}


class OpenRouterClient(BaseLLMClient):
    def __init__(
        self,
        api_key: str,
        model_id: str = "openai/gpt-6-luna",
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 300.0,
        effort: str = EFFORT,
    ) -> None:
        if model_id not in _PRICING_PER_MTOK:
            raise ValueError(f"no pricing recorded for {model_id!r}")
        self.model_id = model_id
        self.effort = effort
        self.provider = _PINNED_PROVIDER[model_id]
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout_s, headers={"Authorization": f"Bearer {api_key}"})
        self.finish_reasons: dict[str, int] = {}
        self.served_by: dict[str, int] = {}

    def _body(self, *, system: str, prompt: str, seed: int, max_tokens: int) -> dict:
        return {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens + REASONING_HEADROOM_TOKENS,
            "reasoning": {"effort": self.effort},
            # Accepted by the model; recorded, not relied on — an API model is
            # not reproducible from a seed.
            "seed": seed,
            "provider": {"order": [self.provider], "allow_fallbacks": False},
        }

    def _generate_impl(
        self, *, system: str, prompt: str, seed: int, max_tokens: int
    ) -> LLMResponse:
        body = self._body(system=system, prompt=prompt, seed=seed, max_tokens=max_tokens)
        start = time.perf_counter()
        try:
            response = self._http.post(f"{self._base_url}/chat/completions", json=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TransientProviderError(str(exc)) from exc
        if response.status_code == 429:
            # Wait out the provider's own reset before the base class retries:
            # its backoff tops out at 30 s, and a per-minute token limit can
            # need longer — otherwise a throttled call becomes an
            # infrastructure_error and the run is lost to a quota, not a result.
            time.sleep(_reset_seconds(response.headers))
        if response.status_code in _TRANSIENT_STATUS:
            raise TransientProviderError(f"HTTP {response.status_code}: {response.text[:200]}")
        if response.is_error:
            # Carry the provider's own message: `raise_for_status()` drops the
            # body, and the body is the diagnosis — Groq's 413 says "Request
            # too large ... TPM: Limit 8000, Requested 17075", which the first
            # Groq attempt lost to a bare "413 Payload Too Large".
            raise httpx.HTTPStatusError(
                f"HTTP {response.status_code} from {self._base_url}: {response.text[:500]}",
                request=response.request,
                response=response,
            )
        latency_s = time.perf_counter() - start
        data = response.json()

        served = str(data.get("provider", "unknown"))
        self.served_by[served] = self.served_by.get(served, 0) + 1
        choice = data["choices"][0]
        reason = str(choice.get("finish_reason"))
        self.finish_reasons[reason] = self.finish_reasons.get(reason, 0) + 1
        # None on a refusal or an empty completion: recorded as the generation
        # failure it is, like the Anthropic arm.
        text = choice["message"].get("content") or ""

        usage = data.get("usage", {})
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))  # includes reasoning
        cost = usage.get("cost")
        cost_usd = float(cost) if cost is not None else self._cost(input_tokens, output_tokens)
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_s=latency_s,
            model_id=self.model_id,
        )

    def count_tokens(self, text: str) -> int:
        # No counting endpoint. The caller uses this for the anti-truncation
        # guard sized for a 16k local context; against a 1M-token context a
        # conservative estimate (≈3 characters per token) is enough.
        return len(text) // 3 + 1

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        input_per_mtok, output_per_mtok = _PRICING_PER_MTOK[self.model_id]
        return (input_tokens * input_per_mtok + output_tokens * output_per_mtok) / 1_000_000


def _reset_seconds(headers: httpx.Headers, cap: float = 90.0) -> float:
    """Seconds until the limit resets, from `retry-after` or the
    `x-ratelimit-reset-*` headers ("6.149s", "1m26.4s"); capped."""
    if (retry_after := headers.get("retry-after")) is not None:
        try:
            return min(float(retry_after), cap)
        except ValueError:
            pass
    waits = []
    for name in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        value = headers.get(name)
        if value and (m := re.fullmatch(r"(?:(\d+)m)?([\d.]+)s", value)):
            waits.append(int(m.group(1) or 0) * 60 + float(m.group(2)))
    return min(min(waits) if waits else 5.0, cap)
