"""Generator backend profiles: one schema, one construction path, three
reachability states, no silent fallback, no credential anywhere.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import qcagent.ui.app as ui
from analysis.compare import IncomparableRunsError, check_comparable
from bench.runner import RunConfig
from qcagent.llm.base import BaseLLMClient
from qcagent.llm.ollama_client import OllamaClient
from qcagent.llm.openai_compatible_client import OpenAICompatibleClient
from qcagent.llm.profiles import (
    Profile,
    ProfileStatus,
    build_client,
    get_profile,
    identity_stamps,
    load_profiles,
    probe,
    redact,
)

SECRET = "sk-test-0123456789-DO-NOT-LEAK"


def _ollama(**kw) -> Profile:
    base = dict(
        name="p",
        label="P",
        client_type="ollama",
        base_url="http://backend:11434",
        model="m:1b",
        expected_server_version="0.35.1",
        determinism={"reset_strategy": "per_run", "temperature": 0.0, "num_ctx": 16384},
    )
    return Profile(**{**base, **kw})


def _openai(**kw) -> Profile:
    base = dict(
        name="frontier",
        label="Frontier",
        client_type="openai_compatible",
        base_url="https://api.example.test/v1",
        model="big-1",
        credential_env="FRONTIER_KEY",
        determinism={"reset_strategy": "none", "temperature": None, "num_ctx": None},
    )
    return Profile(**{**base, **kw})


def _transport(routes: dict[str, tuple[int, dict]], calls: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.path)
        if request.url.path in routes:
            status, body = routes[request.url.path]
            return httpx.Response(status, json=body)
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


# ----------------------------- schema ---------------------------------------


def test_the_shipped_profiles_load_and_carry_their_own_pins() -> None:
    profiles = {p.name: p for p in load_profiles().profiles}
    assert set(profiles) >= {"local-7b", "runpod-30b"}
    assert profiles["local-7b"].expected_server_version == "0.35.1"
    assert profiles["runpod-30b"].expected_server_version == "0.34.4"
    assert (
        profiles["runpod-30b"].setup_hint and "does not start" in profiles["runpod-30b"].setup_hint
    )


def test_an_ollama_profile_must_pin_determinism() -> None:
    with pytest.raises(ValidationError, match="pin temperature and num_ctx"):
        _ollama(determinism={"reset_strategy": "per_run", "temperature": None, "num_ctx": None})


def test_a_credential_value_cannot_be_written_into_a_profile() -> None:
    with pytest.raises(ValidationError, match="NAME of an environment variable"):
        _openai(credential_env=SECRET)


def test_a_url_carrying_credentials_is_rejected() -> None:
    with pytest.raises(ValidationError, match="credentials"):
        _ollama(base_url="http://user:pw@backend:11434")
    with pytest.raises(ValidationError):
        _ollama(base_url="http://backend:11434/?token=abc")


def test_unknown_profile_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _ollama(api_key=SECRET)


def test_an_openai_compatible_endpoint_has_no_version_to_pin() -> None:
    with pytest.raises(ValidationError, match="no server version"):
        _openai(expected_server_version="1.0")


# ------------------- one construction path, no second backend ----------------


def test_an_openai_compatible_profile_is_configuration_only(monkeypatch) -> None:
    """No new code per backend: the SAME build_client returns a BaseLLMClient
    for either client type, and the request body is the generic dialect."""
    monkeypatch.setenv("FRONTIER_KEY", SECRET)
    local = build_client(get_profile("local-7b"))
    frontier = build_client(_openai())

    assert isinstance(local, OllamaClient) and isinstance(frontier, OpenAICompatibleClient)
    assert isinstance(local, BaseLLMClient) and isinstance(frontier, BaseLLMClient)
    body = frontier._body(system="s", prompt="p", seed=3, max_tokens=100)
    assert body["model"] == "big-1" and body["seed"] == 3 and body["max_tokens"] == 100
    # none of OpenRouter's dialect leaks into a generic endpoint
    assert "provider" not in body and "reasoning" not in body
    assert "temperature" not in body  # profile says "not sent"


def test_the_openai_compatible_client_speaks_through_the_shared_base_path() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "qc = 1"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    client = OpenAICompatibleClient(
        SECRET,
        "big-1",
        "https://api.example.test/v1",
        temperature=0.2,
        pricing_usd_per_mtok=(1.0, 2.0),
    )
    client._http = httpx.Client(
        transport=httpx.MockTransport(handler), headers=client._http.headers
    )
    response = client._generate_impl(system="s", prompt="p", seed=1, max_tokens=50)

    assert response.text == "qc = 1" and response.cost_usd == pytest.approx(20 / 1_000_000)
    assert seen["body"]["temperature"] == 0.2
    assert seen["auth"] == f"Bearer {SECRET}"  # sent on the wire, nowhere else


# ----------------------- reachability: three states --------------------------


def test_reachable_with_a_matching_version() -> None:
    http = httpx.Client(
        transport=_transport(
            {
                "/api/version": (200, {"version": "0.35.1"}),
                "/api/tags": (200, {"models": [{"name": "m:1b", "digest": "abc"}]}),
            }
        )
    )
    status = probe(_ollama(), client=http)
    assert (status.state, status.version_gate, status.usable) == ("reachable", "matched", True)
    assert status.server_version == "0.35.1" and status.refusal() is None


def test_reachable_but_a_wrong_version_is_refused_not_overridden_from_the_ui() -> None:
    http = httpx.Client(
        transport=_transport(
            {
                "/api/version": (200, {"version": "0.34.4"}),
                "/api/tags": (200, {"models": [{"name": "m:1b"}]}),
            }
        )
    )
    status = probe(_ollama(), client=http)
    assert status.state == "reachable" and not status.usable
    message = status.refusal() or ""
    assert (
        "0.34.4" in message and "0.35.1" in message and "NOT sent to any other profile" in message
    )


def test_unreachable_names_the_profile_the_reason_and_the_setup_hint() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    http = httpx.Client(transport=httpx.MockTransport(refuse))
    profile = _ollama(name="runpod-x", setup_hint="Needs the pod and tunnel to be up.")
    status = probe(profile, client=http)
    message = status.refusal() or ""
    assert status.state == "unreachable" and not status.usable
    assert "runpod-x" in message and "connection refused" in message
    assert "Needs the pod and tunnel" in message and "NOT sent to any other profile" in message


def test_a_model_that_is_not_pulled_is_unreachable_with_that_reason() -> None:
    http = httpx.Client(
        transport=_transport(
            {
                "/api/version": (200, {"version": "0.35.1"}),
                "/api/tags": (200, {"models": []}),
            }
        )
    )
    status = probe(_ollama(), client=http)
    assert status.state == "unreachable" and "not pulled" in (status.reason or "")


def test_not_configured_when_the_credential_variable_is_unset(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("FRONTIER_KEY", raising=False)
    status = probe(_openai(), env_file=tmp_path / "no.env")
    assert status.state == "not_configured"
    assert "FRONTIER_KEY" in (status.reason or "")  # names the variable, never a value
    assert "not configured" in (status.refusal() or "")


def test_not_configured_when_there_is_no_base_url() -> None:
    status = probe(_ollama(base_url=None))
    assert status.state == "not_configured" and "base URL" in (status.reason or "")


def test_the_openai_probe_authenticates_server_side_and_reports_a_rejected_key(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FRONTIER_KEY", SECRET)
    http = httpx.Client(transport=_transport({"/v1/models": (401, {})}))
    status = probe(_openai(), client=http)
    assert status.state == "unreachable" and "rejected" in (status.reason or "")
    assert SECRET not in repr(status) and SECRET not in (status.refusal() or "")


def test_reachability_is_live_every_time_never_cached() -> None:
    """App first, pod later: a status read once at boot must not stick."""
    calls: list[str] = []
    up = {"on": False}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if not up["on"]:
            raise httpx.ConnectError("down", request=request)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.35.1"})
        return httpx.Response(200, json={"models": [{"name": "m:1b"}]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    first = probe(_ollama(), client=http)
    up["on"] = True
    second = probe(_ollama(), client=http)

    assert first.state == "unreachable" and second.state == "reachable"
    assert first.checked_at and second.checked_at  # when the check ran is carried


# --------------------------- secrets stay server-side ------------------------


def test_redact_removes_the_credential_from_any_string(monkeypatch) -> None:
    monkeypatch.setenv("FRONTIER_KEY", SECRET)
    assert SECRET not in redact(f"upstream said: bad key {SECRET}", _openai())


def test_identity_stamps_name_things_but_carry_no_url_or_credential(monkeypatch) -> None:
    monkeypatch.setenv("FRONTIER_KEY", SECRET)
    status = ProfileStatus(
        profile="p",
        label="P",
        state="reachable",
        server_version="0.35.1",
        version_gate="matched",
        model_digest="abc",
    )
    stamps = identity_stamps(_ollama(), status)
    assert stamps["profile"] == "p" and stamps["model_resolved"] == "m:1b"
    assert stamps["server_version_reported"] == "0.35.1"
    assert stamps["determinism_temperature"] == "0.0" and stamps["determinism_num_ctx"] == "16384"
    flat = " ".join(stamps.values())
    assert "http" not in flat and SECRET not in flat


# ----------------------------- UI: no silent fallback ------------------------


class _Boom:
    def __call__(self, *a, **k):
        raise AssertionError("a client/graph was built for a refused request")


def _statuses(**by_name: ProfileStatus):
    def fake_probe(profile, **_):
        return by_name[profile.name]

    return fake_probe


def _down(name: str, reason: str) -> ProfileStatus:
    return ProfileStatus(profile=name, label=name, state="unreachable", reason=reason)


def _up(name: str) -> ProfileStatus:
    return ProfileStatus(
        profile=name,
        label=name,
        state="reachable",
        server_version="0.35.1",
        expected_server_version="0.35.1",
        version_gate="matched",
    )


def test_profiles_endpoint_shows_three_states_live_and_never_a_url_or_credential(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ui,
        "probe",
        _statuses(
            **{
                "local-7b": _up("local-7b"),
                "runpod-30b": _down("runpod-30b", "connection refused or host unreachable"),
            }
        ),
    )
    body = TestClient(ui.app).get("/api/profiles").json()
    by = {p["name"]: p for p in body["profiles"]}
    assert by["local-7b"]["state"] == "reachable" and by["local-7b"]["usable"] is True
    assert by["runpod-30b"]["state"] == "unreachable" and by["runpod-30b"]["reason"]
    assert all("checked_at" in p for p in body["profiles"])
    raw = json.dumps(body)
    assert "base_url" not in raw and "http" not in raw and "credential" not in raw


def test_an_unreachable_profile_refuses_the_run_and_does_not_fall_back(monkeypatch) -> None:
    probed: list[str] = []

    def fake_probe(profile, **_):
        probed.append(profile.name)
        return _down(profile.name, "connection refused or host unreachable")

    monkeypatch.setattr(ui, "probe", fake_probe)
    monkeypatch.setattr(ui, "services", _Boom())
    monkeypatch.setattr(ui, "run_streaming", _Boom())

    text = TestClient(ui.app).get("/api/run", params={"spec": "bell", "profile": "runpod-30b"}).text

    assert "event: refused" in text and "event: stage" not in text and "event: done" not in text
    assert "runpod-30b" in text and "connection refused" in text
    assert "NOT sent to any other profile" in text
    assert probed == ["runpod-30b"], "no other profile may even be consulted"


def test_the_profile_is_re_probed_before_every_generation(monkeypatch) -> None:
    probed: list[str] = []

    def fake_probe(profile, **_):
        probed.append(profile.name)
        return _up(profile.name)

    monkeypatch.setattr(ui, "probe", fake_probe)
    monkeypatch.setattr(ui, "reset_server_state", lambda profile: None)
    monkeypatch.setattr(ui, "services", lambda profile: object())
    monkeypatch.setattr(
        ui,
        "run_streaming",
        lambda *a, **k: iter([type("E", (), {"kind": "done", "data": {}})()]),
    )
    c = TestClient(ui.app)
    c.get("/api/run", params={"spec": "x", "profile": "local-7b"})
    c.get("/api/run", params={"spec": "x", "profile": "local-7b"})
    assert probed == ["local-7b", "local-7b"]


def test_a_served_run_names_its_generator(monkeypatch) -> None:
    monkeypatch.setattr(ui, "probe", _statuses(**{"local-7b": _up("local-7b")}))
    monkeypatch.setattr(ui, "reset_server_state", lambda profile: None)
    monkeypatch.setattr(ui, "services", lambda profile: object())
    seen: dict = {}

    def fake_run(services, **kw):
        seen.update(kw["generator"])
        return iter([type("E", (), {"kind": "done", "data": {}})()])

    monkeypatch.setattr(ui, "run_streaming", fake_run)
    TestClient(ui.app).get("/api/run", params={"spec": "x", "profile": "local-7b"})
    assert seen["profile"] == "local-7b" and seen["model_resolved"] == "qwen2.5-coder:7b"
    assert seen["server_version_reported"] == "0.35.1"
    assert seen["determinism_reset"] == "per_run"


def test_an_unknown_or_missing_profile_is_refused_not_defaulted(monkeypatch) -> None:
    monkeypatch.setattr(ui, "services", _Boom())
    monkeypatch.setattr(ui, "run_streaming", _Boom())
    c = TestClient(ui.app)
    for params in ({"spec": "x", "profile": "nope"}, {"spec": "x"}):
        text = c.get("/api/run", params=params).text
        assert "event: refused" in text and "event: stage" not in text
    assert c.get("/api/profiles/nope/status").status_code == 404


def test_the_guarantee_report_names_the_generator() -> None:
    from qcagent.ui.session import generator_line

    line = generator_line(
        {
            "profile": "runpod-30b",
            "model_resolved": "qwen3-coder:30b",
            "server_version_reported": "0.34.4",
            "determinism_reset": "per_run",
            "determinism_temperature": "0.0",
            "determinism_num_ctx": "16384",
        }
    )
    assert "runpod-30b" in line and "qwen3-coder:30b" in line and "0.34.4" in line
    assert "not recorded" in generator_line(None)


# ------------------------- runner and comparison -----------------------------


def test_a_profile_is_the_single_source_of_model_url_and_reset() -> None:
    config = RunConfig(profile="runpod-30b", tasks=["bell_phi_plus_2q"], seeds=[1])
    assert config.model == "qwen3-coder:30b" and config.reset_per_run is True
    assert config.ollama_url == "http://localhost:11435"


def test_a_config_cannot_both_name_a_profile_and_a_url() -> None:
    with pytest.raises(ValidationError, match="ollama_base_url"):
        RunConfig(profile="local-7b", ollama_base_url="http://elsewhere:1")
    with pytest.raises(ValidationError, match="unknown generator profile"):
        RunConfig(profile="does-not-exist")


def _rec(**lib):
    from tests.unit.test_compare_guard import _record

    return _record(**lib)


def test_cross_profile_comparison_is_refused() -> None:
    with pytest.raises(IncomparableRunsError, match="profile"):
        check_comparable([_rec(profile="local-7b")], [_rec(profile="runpod-30b")])


def test_two_unprofiled_historical_runs_still_compare() -> None:
    check_comparable([_rec()], [_rec()])


def test_a_profiled_run_never_compares_against_an_unprofiled_one() -> None:
    with pytest.raises(IncomparableRunsError, match="profile"):
        check_comparable([_rec()], [_rec(profile="local-7b")])
    check_comparable([_rec(profile="local-7b")], [_rec(profile="local-7b")])
