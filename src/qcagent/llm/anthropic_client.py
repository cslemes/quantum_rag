"""Fronteira A client — frontier generator accessed via the Anthropic API."""

import time

import anthropic

from qcagent.llm.base import BaseLLMClient, LLMResponse, TransientProviderError

# Transient failures — retried by BaseLLMClient.generate() with backoff
# before surfacing as InfrastructureError (spec edge case, T012b).
_TRANSIENT_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.OverloadedError,
)

# USD per million tokens (input, output). Verify against
# https://www.anthropic.com/pricing before an API-costed pilot or full run
# (constitution: "toda rodada com custo monetário exige piloto extrapolado").
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (3.00, 15.00),
}


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str, model_id: str = "claude-sonnet-4-5") -> None:
        self.model_id = model_id
        self._client = anthropic.Anthropic(api_key=api_key)

    def _generate_impl(
        self, *, system: str, prompt: str, seed: int, max_tokens: int
    ) -> LLMResponse:
        # The Anthropic API has no `seed` parameter — unlike Ollama, output is
        # not deterministically reproducible from a seed alone. `seed` is
        # still threaded through and recorded in RunRecord for experimental
        # bookkeeping; response caching (T012) is what makes a given
        # (prompt, model, seed) triple reproducible in practice.
        start = time.perf_counter()
        try:
            response = self._client.messages.create(
                model=self.model_id,
                system=system,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except _TRANSIENT_EXCEPTIONS as exc:
            raise TransientProviderError(str(exc)) from exc
        latency_s = time.perf_counter() - start
        text = "".join(block.text for block in response.content if block.type == "text")
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost_usd = self._cost(input_tokens, output_tokens)
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_s=latency_s,
            model_id=self.model_id,
        )

    def count_tokens(self, text: str) -> int:
        result = self._client.messages.count_tokens(
            model=self.model_id,
            messages=[{"role": "user", "content": text}],
        )
        return result.input_tokens

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        input_per_mtok, output_per_mtok = _PRICING_PER_MTOK[self.model_id]
        return (input_tokens * input_per_mtok + output_tokens * output_per_mtok) / 1_000_000
