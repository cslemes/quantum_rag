"""Any OpenAI-compatible chat-completions endpoint, from configuration alone.

This is the client a profile with `client_type: openai_compatible` builds. It
is NOT a second generation path: it is `BaseLLMClient` like every other client
(same cache, retry, `InfrastructureError`, accounting), and it reuses the
request/response/transient-error handling of `OpenRouterClient`. What it drops
is everything OpenRouter-specific that a generic endpoint would reject or
ignore: the upstream-provider pin, the reasoning block, the pricing table
keyed by OpenRouter ids.

The API key is a constructor argument held only in the HTTP client's headers.
It is never stored on the instance as an attribute and never formatted into a
message (see `redact`).
"""

import httpx

from qcagent.llm.openrouter_client import OpenRouterClient


class OpenAICompatibleClient(OpenRouterClient):
    def __init__(
        self,
        api_key: str,
        model_id: str,
        base_url: str,
        *,
        temperature: float | None = None,
        pricing_usd_per_mtok: tuple[float, float] | None = None,
        max_tokens_headroom: int = 0,
        timeout_s: float = 300.0,
    ) -> None:
        # Deliberately does not call OpenRouterClient.__init__: it demands an
        # OpenRouter pricing entry and pins an upstream provider.
        self.model_id = model_id
        self.provider = "openai_compatible"
        self.effort = ""
        self.temperature = temperature
        self.pricing = pricing_usd_per_mtok
        self.headroom = max_tokens_headroom
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
            "max_tokens": max_tokens + self.headroom,
            "seed": seed,
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        return body

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        if self.pricing is None:
            return 0.0
        input_per_mtok, output_per_mtok = self.pricing
        return (input_tokens * input_per_mtok + output_tokens * output_per_mtok) / 1_000_000
