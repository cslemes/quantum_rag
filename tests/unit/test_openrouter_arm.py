"""Fronteira B through OpenRouter (no network — httpx.MockTransport).

What is pinned, because each would otherwise be a hidden variable (F15): the
upstream provider (no silent rerouting), reasoning effort, and headroom for
reasoning tokens on top of the nodes' visible budgets.
"""

import json

import httpx
import pytest

from bench.runner import RunConfig
from qcagent.llm.base import TransientProviderError
from qcagent.llm.openrouter_client import EFFORT, REASONING_HEADROOM_TOKENS, OpenRouterClient


def _client(handler) -> OpenRouterClient:
    client = OpenRouterClient(api_key="test", model_id="openai/gpt-6-luna")
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def _ok(request: httpx.Request, *, cost: float | None = 0.00042, content: str | None = "qc = 1"):
    usage = {"prompt_tokens": 1000, "completion_tokens": 300}
    if cost is not None:
        usage["cost"] = cost
    return httpx.Response(
        200,
        json={
            "provider": "OpenAI",
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": usage,
        },
    )


def test_the_request_pins_provider_effort_and_headroom() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return _ok(request)

    response = _client(handler)._generate_impl(system="s", prompt="p", seed=2, max_tokens=512)

    assert seen["provider"] == {"order": ["openai"], "allow_fallbacks": False}
    assert seen["reasoning"] == {"effort": EFFORT}
    assert seen["max_tokens"] == 512 + REASONING_HEADROOM_TOKENS
    assert seen["seed"] == 2
    assert "temperature" not in seen  # not a supported parameter of this model
    assert seen["messages"][0] == {"role": "system", "content": "s"}
    assert response.text == "qc = 1"
    assert response.cost_usd == pytest.approx(0.00042)  # measured cost preferred


def test_cost_falls_back_to_list_price_and_serving_is_counted() -> None:
    client = _client(lambda r: _ok(r, cost=None))
    response = client._generate_impl(system="s", prompt="p", seed=1, max_tokens=100)

    assert response.cost_usd == pytest.approx((1000 * 0.10 + 300 * 0.50) / 1e6)
    assert client.served_by == {"OpenAI": 1}
    assert client.finish_reasons == {"stop": 1}


def test_an_empty_completion_is_an_empty_answer_not_a_crash() -> None:
    response = _client(lambda r: _ok(r, content=None))._generate_impl(
        system="s", prompt="p", seed=1, max_tokens=100
    )
    assert response.text == ""


@pytest.mark.parametrize("status", [429, 503])
def test_rate_limits_and_server_errors_are_transient(status: int) -> None:
    client = _client(lambda r: httpx.Response(status, text="busy"))
    with pytest.raises(TransientProviderError):
        client._generate_impl(system="s", prompt="p", seed=1, max_tokens=100)


def test_an_unpriced_model_cannot_start() -> None:
    with pytest.raises(ValueError, match="no pricing"):
        OpenRouterClient(api_key="test", model_id="openai/unknown")


def test_the_config_must_turn_off_the_ollama_protocol() -> None:
    with pytest.raises(ValueError, match="reset_per_run: false"):
        RunConfig(provider="openrouter", model="openai/gpt-6-luna")
