"""Regression test for `ollama_version` — the host Ollama's version is no
longer pinned by a docker-compose image tag (research.md's "Ambiente de
execução canônico"), so this is the only thing that records it for
`RunRecord.lib_versions` (Principle II).
"""

import httpx
import pytest

from qcagent.llm.ollama_client import ollama_version


def _versioned_response(status_code: int, **kwargs: object) -> httpx.Response:
    request = httpx.Request("GET", "http://host.docker.internal:11434/api/version")
    return httpx.Response(status_code, request=request, **kwargs)


def test_returns_the_reported_version(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, timeout: float) -> httpx.Response:
        assert url == "http://host.docker.internal:11434/api/version"
        return _versioned_response(200, json={"version": "0.4.7"})

    monkeypatch.setattr(httpx, "get", fake_get)

    assert ollama_version("http://host.docker.internal:11434") == "0.4.7"


def test_strips_a_trailing_slash_from_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, timeout: float) -> httpx.Response:
        assert url == "http://host.docker.internal:11434/api/version"
        return _versioned_response(200, json={"version": "0.4.7"})

    monkeypatch.setattr(httpx, "get", fake_get)

    assert ollama_version("http://host.docker.internal:11434/") == "0.4.7"


def test_returns_unknown_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, timeout: float) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", fake_get)

    assert ollama_version("http://host.docker.internal:11434") == "unknown"


def test_returns_unknown_on_non_200_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, timeout: float) -> httpx.Response:
        return _versioned_response(404, text="not found")

    monkeypatch.setattr(httpx, "get", fake_get)

    assert ollama_version("http://host.docker.internal:11434") == "unknown"
