"""Fronteira B through the OpenAI API directly (no network — MockTransport)."""

import json

import httpx
import pytest

from bench.runner import RunConfig
from qcagent.llm.openai_client import OpenAIClient
from qcagent.llm.openrouter_client import REASONING_HEADROOM_TOKENS


def _client(handler, **kwargs) -> OpenAIClient:
    client = OpenAIClient(api_key="test", model_id="gpt-6-luna", **kwargs)
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def _capture(seen: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": "qc = 1"}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 300},
            },
        )

    return handler


def test_openai_dialect_and_messages() -> None:
    seen: dict = {}
    response = _client(_capture(seen))._generate_impl(
        system="s", prompt="p", seed=4, max_tokens=512
    )

    assert seen["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "p"},
    ]
    assert seen["max_completion_tokens"] == 512 + REASONING_HEADROOM_TOKENS
    assert "max_tokens" not in seen
    assert seen["reasoning_effort"] == "high"
    assert seen["seed"] == 4
    assert "temperature" not in seen  # only after a probe shows it is accepted
    assert "provider" not in seen
    assert response.cost_usd == pytest.approx((1000 * 0.10 + 300 * 0.50) / 1e6)


def test_temperature_is_sent_only_when_configured() -> None:
    seen: dict = {}
    _client(_capture(seen), send_temperature=True)._generate_impl(
        system="s", prompt="p", seed=1, max_tokens=10
    )
    assert seen["temperature"] == 0


def test_the_config_must_turn_off_the_ollama_protocol() -> None:
    with pytest.raises(ValueError, match="reset_per_run: false"):
        RunConfig(provider="openai", model="gpt-6-luna")
