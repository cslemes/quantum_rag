"""Fronteira A client — frontier generator accessed via the Anthropic API."""

import time
from typing import Final

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
    "claude-opus-5": (5.00, 25.00),
}

# Thinking is on by default on Claude Opus 5 and shares `max_tokens` with the
# visible answer. The nodes size `max_tokens` for the VISIBLE output of a
# model that does not think (critic 512, planner 2048, generator 4096); passed
# through unchanged, a thinking model would be cut off mid-thought. The
# headroom is added on top, so the nodes' budgets keep meaning what they mean.
THINKING_HEADROOM_TOKENS = 12_000
# Stated, not inherited from the API default (D10b, F15): every parameter that
# changes the output is set explicitly and recorded.
EFFORT: Final = "high"


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str, model_id: str = "claude-opus-5") -> None:
        if model_id not in _PRICING_PER_MTOK:
            # A run whose cost cannot be computed is not allowed to start
            # (constitution: every API-costed run is extrapolated from a pilot).
            raise ValueError(f"no pricing recorded for {model_id!r}")
        self.model_id = model_id
        self._client = anthropic.Anthropic(api_key=api_key)
        self.stop_reasons: dict[str, int] = {}

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
                max_tokens=max_tokens + THINKING_HEADROOM_TOKENS,
                thinking={"type": "adaptive"},
                output_config={"effort": EFFORT},
                messages=[{"role": "user", "content": prompt}],
            )
        except _TRANSIENT_EXCEPTIONS as exc:
            raise TransientProviderError(str(exc)) from exc
        latency_s = time.perf_counter() - start
        # Counted, not handled: a refusal or a truncation comes back as short
        # or empty text, which the pipeline then treats as a generation
        # failure — the honest outcome for an experimental arm. No
        # server-side model fallback: it would mix two models in one arm.
        reason = str(response.stop_reason)
        self.stop_reasons[reason] = self.stop_reasons.get(reason, 0) + 1
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
