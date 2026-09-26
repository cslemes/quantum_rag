"""Fronteira B through Groq — the maintainer's provider (2026-09-26).

Groq speaks the OpenAI chat-completions protocol and serves each model
itself, so there is no upstream rerouting to pin (OpenRouter's `provider`
field does not apply). Two parameters improve parity with the local qwen
arm over the OpenRouter models: Groq accepts `temperature` (set to 0, as
qwen's is) and `seed`. Reasoning cannot be switched off on gpt-oss:
`reasoning_effort` is `low` | `medium` | `high` (the API rejects anything
else), so the reduced-reasoning arm runs at `low`, not at none.
"""

from qcagent.llm.openrouter_client import REASONING_HEADROOM_TOKENS, OpenRouterClient

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"

# USD per million tokens (input, output). UNVERIFIED: Groq's pricing page is
# not fetchable in a parseable form from the sandbox and the API returns no
# per-call cost. These are the maintainer's to confirm before a number is
# quoted as cost; on Groq's free tier the actual charge is zero.
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
}


class GroqClient(OpenRouterClient):
    def __init__(
        self,
        api_key: str,
        model_id: str = "openai/gpt-oss-120b",
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 300.0,
        effort: str = "high",
    ) -> None:
        if model_id not in _PRICING_PER_MTOK:
            raise ValueError(f"no pricing recorded for {model_id!r}")
        if effort not in ("low", "medium", "high"):
            raise ValueError(f"gpt-oss reasoning_effort must be low|medium|high, not {effort!r}")
        # Bypass OpenRouterClient's own pricing/provider tables; reuse its
        # request, retry and accounting logic.
        import httpx

        self.model_id = model_id
        self.effort = effort
        self.provider = "groq"
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout_s, headers={"Authorization": f"Bearer {api_key}"})
        self.finish_reasons = {}
        self.served_by = {}

    def _body(self, *, system: str, prompt: str, seed: int, max_tokens: int) -> dict:
        return {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens + REASONING_HEADROOM_TOKENS,
            "reasoning_effort": self.effort,
            "temperature": 0,  # matches the qwen arm (F15)
            "seed": seed,
        }

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        input_per_mtok, output_per_mtok = _PRICING_PER_MTOK[self.model_id]
        return (input_tokens * input_per_mtok + output_tokens * output_per_mtok) / 1_000_000
