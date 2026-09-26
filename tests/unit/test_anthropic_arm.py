"""The frontier arm's configuration (no API calls — the SDK is stubbed).

The arm answers "is the bottleneck the architecture or the generator?", so
everything but the LLM is held fixed, and every parameter that changes the
model's output is stated, not inherited (D10b, F15).
"""

from types import SimpleNamespace

import pytest

from bench.runner import RunConfig
from qcagent.llm.anthropic_client import EFFORT, THINKING_HEADROOM_TOKENS, AnthropicClient


class _StubMessages:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="qc = 1")],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
            stop_reason="end_turn",
        )


def _client() -> tuple[AnthropicClient, _StubMessages]:
    client = AnthropicClient(api_key="test", model_id="claude-sonnet-5")
    stub = _StubMessages()
    client._client = SimpleNamespace(messages=stub)  # type: ignore[assignment]
    return client, stub


def test_thinking_and_effort_are_explicit_and_headroom_is_added() -> None:
    client, stub = _client()
    response = client._generate_impl(system="s", prompt="p", seed=1, max_tokens=512)

    assert stub.kwargs["thinking"] == {"type": "adaptive"}
    assert stub.kwargs["output_config"] == {"effort": EFFORT}
    # The critic's 512 is a VISIBLE budget; thinking gets its own on top.
    assert stub.kwargs["max_tokens"] == 512 + THINKING_HEADROOM_TOKENS
    assert "temperature" not in stub.kwargs  # rejected by the model
    assert response.text == "qc = 1"  # thinking blocks are not the answer
    assert response.cost_usd == pytest.approx((1000 * 2 + 200 * 10) / 1e6)
    assert client.stop_reasons == {"end_turn": 1}


def test_an_unpriced_model_cannot_start() -> None:
    with pytest.raises(ValueError, match="no pricing"):
        AnthropicClient(api_key="test", model_id="claude-unknown")


def test_the_ollama_protocol_must_be_turned_off_explicitly() -> None:
    """Reset and canary are properties of the local Ollama server (F28); the
    config has to say they do not apply, not have them silently skipped."""
    with pytest.raises(ValueError, match="reset_per_run: false"):
        RunConfig(provider="anthropic", model="claude-sonnet-5")
    RunConfig(
        provider="anthropic", model="claude-sonnet-5", reset_per_run=False, protocol_canary=[]
    )
