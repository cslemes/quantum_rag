"""D10c's guard, which had never run (F21).

data-model.md stated the rule: `gpu_processor == "100% GPU"` on the local arm,
else abort. `assert_full_gpu_offload` existed in code and was never called —
and could not have worked anyway, because it shells out to `ollama ps` and
`nvidia-smi`, which live on the Windows host while the agent reaches Ollama
only over HTTP. `RunRecord.gpu_processor` is None in all 360 records of every
run ever made.

An offloaded generator makes the latency numbers meaningless, and SC-007 IS a
latency number.
"""

import httpx
import pytest

from qcagent.llm.ollama_client import (
    GPUOffloadError,
    assert_full_gpu_offload_http,
    gpu_offload_fraction,
)

URL = "http://generator.invalid:11434"
MODEL = "qwen2.5-coder:7b"


class _Transport(httpx.BaseTransport):
    def __init__(self, payload) -> None:
        self.payload = payload

    def handle_request(self, request):
        import json

        return httpx.Response(200, content=json.dumps(self.payload).encode())


def _patch(monkeypatch, payload) -> None:
    client = httpx.Client(transport=_Transport(payload))
    monkeypatch.setattr(httpx, "get", lambda url, **kw: client.get(url))


def test_a_fully_offloaded_model_passes_and_reports_the_fraction(monkeypatch) -> None:
    _patch(monkeypatch, {"models": [{"name": MODEL, "size": 100, "size_vram": 100}]})
    assert assert_full_gpu_offload_http(URL, MODEL) == 1.0


def test_a_partially_offloaded_model_aborts(monkeypatch) -> None:
    """The case the guard exists for: the run would otherwise complete and
    produce a latency figure that means nothing."""
    _patch(monkeypatch, {"models": [{"name": MODEL, "size": 100, "size_vram": 60}]})

    with pytest.raises(GPUOffloadError, match="60%"):
        assert_full_gpu_offload_http(URL, MODEL)


def test_an_unloaded_model_aborts_rather_than_passing(monkeypatch) -> None:
    """ "Cannot determine" must never read as "fine" — the same tri-state rule
    the verdicts follow. `/api/ps` reports nothing for an unloaded model."""
    _patch(monkeypatch, {"models": []})

    assert gpu_offload_fraction(URL, MODEL) is None
    with pytest.raises(GPUOffloadError, match="not loaded"):
        assert_full_gpu_offload_http(URL, MODEL)


def test_an_unreachable_server_does_not_silently_pass(monkeypatch) -> None:
    def boom(url, **kw):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", boom)
    assert gpu_offload_fraction(URL, MODEL) is None
    with pytest.raises(GPUOffloadError):
        assert_full_gpu_offload_http(URL, MODEL)


def test_the_suite_records_what_the_guard_measured() -> None:
    """A guard whose result is not recorded is only half a guard — the exact
    F21 pattern this fixes."""
    from pathlib import Path

    source = Path("bench/runner.py").read_text()
    assert '"gpu_offload"' in source
    assert source.count("verify_gpu_offload(config.ollama_url") == 1, (
        "called exactly once: the check needs the model loaded, the reset unloads it, "
        "and a second call would re-warm it and change the state the run starts from"
    )
