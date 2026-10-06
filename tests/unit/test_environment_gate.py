"""Version gate: the runner refuses a server that is not the pinned one, an
override is stamped into the record, and the GPU model is recorded as
DECLARED (Ollama's HTTP API exposes no device name)."""

from pathlib import Path

import pytest

from bench.runner import EnvironmentMismatchError, RunConfig, check_environment

PIN = Path("bench/environment.yaml")


def _config(**kwargs) -> RunConfig:
    return RunConfig(tasks=["bell_phi_plus_2q"], seeds=[1], **kwargs)


def test_matching_version_passes_and_is_stamped() -> None:
    stamps = check_environment(_config(), {"ollama": "0.35.1"}, declared_gpu=None)
    assert stamps["ollama_version_gate"] == "matched"
    assert stamps["ollama_expected"] == "0.35.1"


def test_mismatch_aborts_naming_both_versions() -> None:
    with pytest.raises(EnvironmentMismatchError) as exc:
        check_environment(_config(), {"ollama": "0.34.4"})
    assert "0.35.1" in str(exc.value) and "0.34.4" in str(exc.value)


def test_unreachable_server_is_a_mismatch_not_a_pass() -> None:
    with pytest.raises(EnvironmentMismatchError):
        check_environment(_config(), {"ollama": "unknown"})
    with pytest.raises(EnvironmentMismatchError):
        check_environment(_config(), {})


def test_override_runs_but_is_stamped_as_overridden() -> None:
    stamps = check_environment(
        _config(allow_ollama_version_mismatch=True), {"ollama": "0.34.4"}
    )
    gate = stamps["ollama_version_gate"]
    assert gate.startswith("OVERRIDDEN")
    assert "0.35.1" in gate and "0.34.4" in gate


def test_config_can_pin_its_own_version_for_the_pod() -> None:
    stamps = check_environment(
        _config(expected_ollama_version="0.34.4", generator_host="runpod:x"),
        {"ollama": "0.34.4"},
    )
    assert stamps["ollama_version_gate"] == "matched"
    with pytest.raises(EnvironmentMismatchError):
        check_environment(_config(expected_ollama_version="0.34.4"), {"ollama": "0.35.1"})


def test_gpu_is_declared_not_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QCAGENT_GPU_MODEL", raising=False)
    absent = check_environment(_config(), {"ollama": "0.35.1"}, declared_gpu=None)
    assert absent["gpu_model"] == "unrecorded"
    declared = check_environment(
        _config(), {"ollama": "0.35.1"}, declared_gpu="NVIDIA GeForce RTX 3070 (8 GB)"
    )
    assert declared["gpu_model"] == "NVIDIA GeForce RTX 3070 (8 GB)"
    assert "not verified" in declared["gpu_model_status"]


def test_a_gpu_declaration_that_contradicts_the_pin_aborts() -> None:
    with pytest.raises(EnvironmentMismatchError):
        check_environment(_config(), {"ollama": "0.35.1"}, declared_gpu="NVIDIA RTX A5000")


def test_api_providers_have_no_server_to_gate() -> None:
    config = RunConfig(
        provider="openai", tasks=["bell_phi_plus_2q"], seeds=[1],
        reset_per_run=False, protocol_canary=[],
    )
    assert "not applicable" in check_environment(config, {})["ollama_version_gate"]
