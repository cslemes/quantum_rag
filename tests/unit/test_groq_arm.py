"""Fronteira B through Groq (no network — httpx.MockTransport)."""

import json

import httpx
import pytest

from bench.runner import RunConfig
from qcagent.llm import openrouter_client
from qcagent.llm.base import TransientProviderError
from qcagent.llm.groq_client import GroqClient
from qcagent.llm.openrouter_client import REASONING_HEADROOM_TOKENS, _reset_seconds


def _client(handler, effort: str = "high") -> GroqClient:
    client = GroqClient(api_key="test", model_id="openai/gpt-oss-120b", effort=effort)
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"finish_reason": "stop", "message": {"content": "qc = 1", "reasoning": "..."}}
            ],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 300},
        },
    )


def test_the_request_matches_the_qwen_arm_where_groq_allows() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return _ok(request)

    response = _client(handler)._generate_impl(system="s", prompt="p", seed=3, max_tokens=512)

    assert seen["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "p"},
    ]
    assert seen["temperature"] == 0  # as the qwen arm
    assert seen["seed"] == 3
    assert seen["reasoning_effort"] == "high"
    assert seen["max_tokens"] == 512 + REASONING_HEADROOM_TOKENS
    assert "provider" not in seen  # OpenRouter-only field
    assert response.text == "qc = 1"  # reasoning is not the answer
    assert response.cost_usd == pytest.approx((1000 * 0.15 + 300 * 0.60) / 1e6)


def test_reasoning_cannot_be_turned_off_on_gpt_oss() -> None:
    """The API rejects anything but low|medium|high (probed 2026-09-26), so the
    reduced-reasoning arm is `low` and says so."""
    with pytest.raises(ValueError, match="low|medium|high"):
        GroqClient(api_key="test", effort="none")


def test_a_429_waits_out_the_providers_reset_before_retrying(monkeypatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr(openrouter_client.time, "sleep", slept.append)
    client = _client(
        lambda r: httpx.Response(429, headers={"x-ratelimit-reset-tokens": "6.5s"}, text="slow")
    )
    with pytest.raises(TransientProviderError):
        client._generate_impl(system="s", prompt="p", seed=1, max_tokens=10)
    assert slept == [6.5]


@pytest.mark.parametrize(
    ("headers", "seconds"),
    [
        ({"retry-after": "12"}, 12.0),
        ({"x-ratelimit-reset-tokens": "1m26.4s"}, 86.4),
        ({"x-ratelimit-reset-tokens": "9m0s"}, 90.0),  # capped
        ({}, 5.0),
    ],
)
def test_reset_parsing(headers: dict, seconds: float) -> None:
    assert _reset_seconds(httpx.Headers(headers)) == pytest.approx(seconds)


def test_the_config_must_turn_off_the_ollama_protocol() -> None:
    with pytest.raises(ValueError, match="reset_per_run: false"):
        RunConfig(provider="groq", model="openai/gpt-oss-120b")
