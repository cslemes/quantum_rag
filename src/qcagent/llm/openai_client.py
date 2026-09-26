"""Fronteira B through the OpenAI API directly (maintainer's choice, 2026-09-26).

OpenRouter is unreachable from the sandbox (the proxy strips the
Authorization header); api.openai.com receives it — verified with a dummy
key, which came back "Incorrect API key provided" rather than "no key".

Same request/retry/accounting path as the OpenRouter client, OpenAI's own
dialect: `max_completion_tokens` (reasoning tokens share it, so the same
headroom is added on top of the nodes' visible budgets) and top-level
`reasoning_effort`. OpenAI serves its models itself, so there is no upstream
provider to pin. `temperature` is NOT sent unless `send_temperature` is set:
reasoning models commonly reject it, and whether these do is settled by a
probe before any arm runs, not assumed.
"""

import httpx

from qcagent.llm.openrouter_client import REASONING_HEADROOM_TOKENS, OpenRouterClient

DEFAULT_BASE_URL = "https://api.openai.com/v1"

# USD per million tokens (input, output): OpenAI's list prices as mirrored by
# OpenRouter's /api/v1/models on 2026-09-26. The OpenAI API returns no
# per-call cost, so this table is the cost; confirm against OpenAI's pricing
# page before quoting.
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6-sol": (2.00, 10.00),
}


class OpenAIClient(OpenRouterClient):
    def __init__(
        self,
        api_key: str,
        model_id: str = "gpt-6-luna",
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 300.0,
        effort: str = "high",
        send_temperature: bool = False,
    ) -> None:
        if model_id not in _PRICING_PER_MTOK:
            raise ValueError(f"no pricing recorded for {model_id!r}")
        self.model_id = model_id
        self.effort = effort
        self.send_temperature = send_temperature
        self.provider = "openai"
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout_s, headers={"Authorization": f"Bearer {api_key}"})
        self.finish_reasons: dict[str, int] = {}
        self.served_by: dict[str, int] = {}

    def _body(self, *, system: str, prompt: str, seed: int, max_tokens: int) -> dict:
        body: dict = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": max_tokens + REASONING_HEADROOM_TOKENS,
            "reasoning_effort": self.effort,
            "seed": seed,
        }
        if self.send_temperature:
            body["temperature"] = 0  # matches the qwen arm (F15)
        return body

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        input_per_mtok, output_per_mtok = _PRICING_PER_MTOK[self.model_id]
        return (input_tokens * input_per_mtok + output_tokens * output_per_mtok) / 1_000_000
