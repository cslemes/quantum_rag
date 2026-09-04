"""Regression test for the anti-truncation guard (T011b, research.md D10b).

Ollama's default context (4096) truncates a too-long prompt silently — no
error, no log. That failure hits condition C5 (RAG, the longest prompts)
while leaving C1 untouched, which would make the experiment measure "RAG
doesn't help" when the retrieved chunks never reached the model — silently
invalidating H1/H3.

These tests prove two things a smoke test wouldn't catch on its own:
  1. the guard raises a real exception, not a warning or log line;
  2. it fires BEFORE the HTTP request — mocking the transport and asserting
     it was never called is what rules out "it happened to fail downstream
     for an unrelated reason and the test passed anyway."
"""

from unittest.mock import MagicMock

import httpx
import pytest

from qcagent.llm.ollama_client import ContextOverflowError, OllamaClient

NUM_CTX = 50  # small and unambiguous: a couple hundred chars is enough to overflow it


def _client_with_mocked_transport() -> tuple[OllamaClient, MagicMock]:
    client = OllamaClient(base_url="http://localhost:11434", num_ctx=NUM_CTX)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "ok"},
        "prompt_eval_count": 5,
        "eval_count": 2,
    }
    mock_post = MagicMock(return_value=mock_response)
    client._client.post = mock_post
    return client, mock_post


def test_over_length_prompt_raises_before_http_call() -> None:
    client, mock_post = _client_with_mocked_transport()

    # count_tokens() estimates ~len(text)//4; this is ~250 estimated tokens,
    # well past NUM_CTX=50 — no ambiguity about which side of the threshold
    # it lands on.
    over_length_prompt = "word " * 200

    with pytest.raises(ContextOverflowError):
        client._generate_impl(system="", prompt=over_length_prompt, seed=0, max_tokens=16)

    # The whole point of the guard is refusing to send — if the transport
    # was invoked, the guard didn't actually fire first, regardless of
    # whether an exception happened to surface anyway.
    mock_post.assert_not_called()


def test_under_length_prompt_reaches_transport() -> None:
    client, mock_post = _client_with_mocked_transport()

    short_prompt = "hi"  # a couple of estimated tokens, comfortably under NUM_CTX

    response = client._generate_impl(system="", prompt=short_prompt, seed=0, max_tokens=16)

    mock_post.assert_called_once()
    assert response.text == "ok"


def test_non_transient_http_error_surfaces_body_and_pull_hint() -> None:
    """A 404 from /api/chat almost always means the model was never pulled.
    httpx's default HTTPStatusError message drops the response body — that's
    exactly where Ollama says so. This regression test exists because that
    detail was silently lost, producing a bare traceback with no actionable
    information for a very common setup mistake."""
    client = OllamaClient(base_url="http://localhost:11434", model_id="qwen2.5-coder:7b")
    request = httpx.Request("POST", "http://localhost:11434/api/chat")
    response = httpx.Response(
        404,
        request=request,
        text='{"error":"model \'qwen2.5-coder:7b\' not found, try pulling it first"}',
    )
    client._client.post = MagicMock(return_value=response)

    with pytest.raises(RuntimeError) as exc_info:
        client._generate_impl(system="", prompt="hi", seed=0, max_tokens=16)

    message = str(exc_info.value)
    assert "404" in message
    assert "not found, try pulling it first" in message
    assert "ollama pull qwen2.5-coder:7b" in message
