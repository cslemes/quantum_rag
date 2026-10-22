"""Version gate, per PROFILE: the runner refuses a server that is not the one
the profile pins, an override is stamped into the record, and the GPU model is
recorded as DECLARED (Ollama's HTTP API exposes no device name).

The expected version lives in the profile, not globally: the host and the pod
pin different Ollama versions, and a global pin would force an override — and
the OVERRIDDEN stamp — on a correct RunPod run.
"""

import pytest

from bench.runner import EnvironmentMismatchError, RunConfig, check_environment


def _config(profile: str | None = "local-7b", **kwargs) -> RunConfig:
    return RunConfig(profile=profile, tasks=["bell_phi_plus_2q"], seeds=[1], **kwargs)


def test_matching_version_passes_and_is_stamped() -> None:
    stamps = check_environment(_config(), {"ollama": "0.35.1"}, declared_gpu=None)
    assert stamps["ollama_version_gate"] == "matched"
    assert stamps["ollama_expected"] == "0.35.1"


def test_mismatch_aborts_naming_the_profile_and_both_versions() -> None:
    with pytest.raises(EnvironmentMismatchError) as exc:
        check_environment(_config(), {"ollama": "0.34.4"})
    message = str(exc.value)
    assert "local-7b" in message and "0.35.1" in message and "0.34.4" in message


def test_unreachable_server_is_a_mismatch_not_a_pass() -> None:
    with pytest.raises(EnvironmentMismatchError):
        check_environment(_config(), {"ollama": "unknown"})
    with pytest.raises(EnvironmentMismatchError):
        check_environment(_config(), {})


def test_override_runs_but_is_stamped_as_overridden() -> None:
    stamps = check_environment(_config(allow_ollama_version_mismatch=True), {"ollama": "0.34.4"})
    gate = stamps["ollama_version_gate"]
    assert gate.startswith("OVERRIDDEN")
    assert "0.35.1" in gate and "0.34.4" in gate


def test_a_correct_runpod_run_is_not_stamped_overridden() -> None:
    """The reason the pin moved into the profile: with a single global pin of
    0.35.1, the pod's legitimate 0.34.4 would need the override flag."""
    stamps = check_environment(_config("runpod-30b"), {"ollama": "0.34.4"})
    assert stamps["ollama_version_gate"] == "matched"
    assert "OVERRIDDEN" not in "".join(stamps.values())


def test_each_profile_refuses_the_other_profiles_version() -> None:
    with pytest.raises(EnvironmentMismatchError):
        check_environment(_config("runpod-30b"), {"ollama": "0.35.1"})
    with pytest.raises(EnvironmentMismatchError):
        check_environment(_config("local-7b"), {"ollama": "0.34.4"})


def test_an_unprofiled_ollama_run_cannot_be_gated_so_it_is_refused() -> None:
    with pytest.raises(EnvironmentMismatchError, match="profile"):
        check_environment(_config(None), {"ollama": "0.35.1"})


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
        provider="openai",
        tasks=["bell_phi_plus_2q"],
        seeds=[1],
        reset_per_run=False,
        protocol_canary=[],
    )
    assert "not applicable" in check_environment(config, {})["ollama_version_gate"]


def test_graph_runner_itself_refuses_an_unprofiled_ollama_run() -> None:
    """Calls `_graph_runner` directly, so it does NOT pass through
    check_environment. The refusal must be local: a guarantee that holds only
    because an upstream check fires first breaks silently when that check is
    reordered or made conditional."""
    from bench.runner import Usage, _graph_runner
    from qcagent.llm.profiles import ProfileError

    config = RunConfig(provider="ollama")
    assert config.profile is None
    with pytest.raises(ProfileError, match="unprofiled Ollama run is not permitted"):
        _graph_runner(config, Usage())
