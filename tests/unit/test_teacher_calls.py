"""Teacher profile, cache key, per-call provenance and the refusal state machine.

Nothing here touches the network: the HTTP layer is an `httpx.MockTransport`
that records every request it receives, so "exactly one request" and "the flag
was in every body" are assertions about what was actually sent.
"""

import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from qcagent.distill.teacher import (
    PipelineHalt,
    RefusalBreaker,
    TeacherConfigError,
    TeacherOutcome,
    TeacherState,
    call_teacher,
    require_teacher_client,
)
from qcagent.llm.openai_compatible_client import OpenAICompatibleClient
from qcagent.llm.profiles import (
    Profile,
    ProfileError,
    ProviderOptions,
    build_client,
)
from qcagent.llm.provenance import RETURNED_NULL, UNAVAILABLE, pick

SECRET = "sk-or-SECRET-VALUE-0123456789"
FLAG = {"enforce_distillable_text": True}


def _completion(**overrides) -> dict:
    data = {
        "id": "gen-123",
        "model": "vendor/big-model",
        "provider": "SomeProvider",
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "CODE"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "cost": 0.0123},
    }
    data.update(overrides)
    return data


class _Server:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.bodies: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content))
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def _client(server: _Server, tmp_path: Path, options: dict | None = FLAG):
    client = OpenAICompatibleClient(
        SECRET, "vendor/big-model", "https://openrouter.example/api/v1", provider_options=options
    )
    client._http = httpx.Client(transport=httpx.MockTransport(server))
    client.cache_dir = tmp_path
    return client


def _call(client, sid="s1"):
    return call_teacher(
        client, statement_id=sid, system="sys", prompt="prompt", seed=1, max_tokens=100
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _s: None)


# ---------------------------------------------------------------- the profile


def _teacher_profile(**over) -> dict:
    base = dict(
        name="teacher-x",
        label="t",
        client_type="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        model="vendor/big-model-1017",
        credential_env="OPENROUTER_API_KEY",
        role="teacher",
        reasoning_effort="high",
        provider_options={"enforce_distillable_text": True},
    )
    base.update(over)
    return base


def test_a_teacher_profile_without_the_flag_cannot_exist() -> None:
    Profile.model_validate(_teacher_profile())
    for options in (None, {}, {"enforce_distillable_text": False}):
        with pytest.raises(ValidationError, match="enforce_distillable_text"):
            Profile.model_validate(_teacher_profile(provider_options=options))


def test_provider_options_are_named_keys_only() -> None:
    with pytest.raises(ValidationError):
        ProviderOptions.model_validate({"order": ["x"]})
    with pytest.raises(ValidationError):
        ProviderOptions.model_validate({"enforce_distillable_text": True, "anything": 1})


def test_a_teacher_must_be_a_hosted_api_with_a_credential() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate(
            _teacher_profile(client_type="ollama", credential_env=None, provider_options=None)
        )


def test_build_client_refuses_a_teacher_that_bypassed_the_validators(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(f"OPENROUTER_API_KEY={SECRET}\n")
    bypassed = Profile.model_construct(**{**_teacher_profile(), "provider_options": None})
    with pytest.raises(ProfileError, match="teacher profile without"):
        build_client(bypassed, env_file=env)
    ok = Profile.model_validate(_teacher_profile())
    client = build_client(ok, env_file=env)
    require_teacher_client(client, ok)


def test_a_generator_client_is_not_a_teacher(tmp_path: Path) -> None:
    client = _client(_Server(httpx.Response(200, json=_completion())), tmp_path, options=None)
    with pytest.raises(TeacherConfigError):
        require_teacher_client(client)


# ------------------------------------------------------ the request and the key


def test_the_flag_is_in_the_body_that_is_actually_sent(tmp_path: Path) -> None:
    server = _Server(httpx.Response(200, json=_completion()))
    outcome = _call(_client(server, tmp_path))
    assert server.bodies[0]["provider"] == FLAG
    assert outcome.response.provenance["provider_options_sent"] == FLAG


def test_provider_options_are_part_of_the_cache_key(tmp_path: Path) -> None:
    """A miss is repaired by re-running; a wrong hit cannot be repaired."""
    plain = _client(_Server(httpx.Response(200, json=_completion())), tmp_path, options=None)
    plain.generate(system="sys", prompt="prompt", seed=1, max_tokens=100)
    flagged_server = _Server(httpx.Response(200, json=_completion()))
    flagged = _client(flagged_server, tmp_path)
    flagged.generate(system="sys", prompt="prompt", seed=1, max_tokens=100)
    assert flagged.last_call_cache_hit is False and len(flagged_server.bodies) == 1
    again_server = _Server(httpx.Response(200, json=_completion()))
    again = _client(again_server, tmp_path)
    again.generate(system="sys", prompt="prompt", seed=1, max_tokens=100)
    assert again.last_call_cache_hit is True and again_server.bodies == []


# ----------------------------------------------------------------- provenance


def test_provenance_records_requested_served_and_raw_metadata(tmp_path: Path) -> None:
    outcome = _call(_client(_Server(httpx.Response(200, json=_completion())), tmp_path))
    prov = outcome.response.provenance
    assert prov["requested_model"] == "vendor/big-model"
    assert prov["derived"]["served_model"] == "vendor/big-model"
    assert prov["derived"]["served_provider"] == "SomeProvider"
    assert prov["derived"]["reported_cost"] == 0.0123
    assert prov["derived_from"]["served_model"] == "model"
    meta = prov["response_metadata"]
    assert meta["id"] == "gen-123" and meta["usage"]["completion_tokens"] == 20
    assert "content" not in meta["choices"][0]["message"]
    assert "choices.0.message.content" in meta["_content_keys_removed"]
    assert outcome.served_model_differs is False


def test_absent_is_unavailable_and_null_is_a_different_fact(tmp_path: Path) -> None:
    data = _completion(provider=None)
    del data["model"]
    del data["id"]
    outcome = _call(_client(_Server(httpx.Response(200, json=data)), tmp_path))
    derived = outcome.response.provenance["derived"]
    assert derived["served_model"] == UNAVAILABLE
    assert derived["generation_id"] == UNAVAILABLE
    assert derived["served_provider"] == RETURNED_NULL
    assert None not in derived.values()
    assert outcome.served_model_differs is None  # unknown is not "same"


def test_pick_walks_lists_and_never_returns_none() -> None:
    assert (
        pick({"choices": [{"finish_reason": "stop"}]}, ("choices", "0", "finish_reason")) == "stop"
    )
    assert pick({"choices": []}, ("choices", "0", "finish_reason")) == UNAVAILABLE
    assert pick({"a": None}, ("a",)) == RETURNED_NULL


def test_a_different_served_model_is_recorded_not_hidden(tmp_path: Path) -> None:
    data = _completion(model="vendor/other-model")
    outcome = _call(_client(_Server(httpx.Response(200, json=data)), tmp_path))
    assert outcome.state is TeacherState.RESPONDED
    assert outcome.served_model_differs is True


def test_no_credential_reaches_a_record(tmp_path: Path) -> None:
    outcome = _call(_client(_Server(httpx.Response(200, json=_completion())), tmp_path))
    dumped = json.dumps(outcome.response.model_dump(), default=str)
    for entry in tmp_path.glob("*.json"):
        dumped += entry.read_text()
    assert SECRET not in dumped


# ----------------------------------------------------------- the state machine


def test_a_refusal_is_one_request_and_never_a_flagless_second(tmp_path: Path) -> None:
    body = {"error": {"code": 404, "message": "No endpoints found matching your data policy"}}
    server = _Server(httpx.Response(404, json=body))
    outcome = _call(_client(server, tmp_path))
    assert outcome.state is TeacherState.REFUSED and outcome.reason_code == "http_404"
    assert outcome.detail["error_code"] == 404 and "data policy" in outcome.detail["error_message"]
    assert len(server.bodies) == 1
    assert all(b["provider"] == FLAG for b in server.bodies)
    assert not list(tmp_path.glob("*.json")), "a refusal must not be cached"


def test_a_transient_failure_is_retried_with_the_same_flagged_body(tmp_path: Path) -> None:
    server = _Server(httpx.Response(429, text="slow down"), httpx.Response(200, json=_completion()))
    outcome = _call(_client(server, tmp_path))
    assert outcome.state is TeacherState.RESPONDED
    assert len(server.bodies) == 2
    assert all(b["provider"] == FLAG for b in server.bodies)


def test_exhausted_retries_are_infrastructure_not_a_verdict(tmp_path: Path) -> None:
    server = _Server(httpx.Response(503, text="down"))
    outcome = _call(_client(server, tmp_path))
    assert outcome.state is TeacherState.INFRASTRUCTURE_FAILED
    assert all(b["provider"] == FLAG for b in server.bodies)


@pytest.mark.parametrize("status,reason", [(402, "credits"), (401, "auth"), (403, "auth")])
def test_credits_and_auth_are_hard_stops(tmp_path: Path, status: int, reason: str) -> None:
    outcome = _call(_client(_Server(httpx.Response(status, text="no")), tmp_path))
    assert outcome.state is TeacherState.HARD_STOP and outcome.reason_code == reason
    with pytest.raises(PipelineHalt):
        RefusalBreaker().record(outcome)


def test_an_errored_choice_is_a_provider_error_and_is_never_cached(tmp_path: Path) -> None:
    data = _completion(
        choices=[{"finish_reason": "error", "error": {"code": 502, "message": "upstream"}}]
    )
    outcome = _call(_client(_Server(httpx.Response(200, json=data)), tmp_path))
    assert outcome.state is TeacherState.PROVIDER_ERROR
    assert outcome.detail["provenance"]["derived"]["choice_error"]["code"] == 502
    assert not list(tmp_path.glob("*.json"))


def test_the_breaker_halts_on_consecutive_refusals_only() -> None:
    refused = TeacherOutcome("s", TeacherState.REFUSED, reason_code="http_404")
    fine = TeacherOutcome("s", TeacherState.RESPONDED)
    breaker = RefusalBreaker(consecutive_limit=3)
    breaker.record(refused)
    breaker.record(refused)
    breaker.record(fine)  # a success resets the run
    breaker.record(refused)
    breaker.record(refused)
    with pytest.raises(PipelineHalt, match="not distillable"):
        breaker.record(refused)


def test_a_response_whose_sent_request_lacked_the_flag_is_nonconforming(tmp_path: Path) -> None:
    client = _client(_Server(httpx.Response(200, json=_completion())), tmp_path)
    client.provider_options = json.dumps(FLAG)  # passes the pre-check
    original = client._body

    def stripped(**kw):
        body = original(**kw)
        body.pop("provider")
        return body

    client._body = stripped  # type: ignore[method-assign]
    outcome = _call(client)
    assert outcome.state is TeacherState.NONCONFORMING


def test_teacher_profiles_are_not_generators() -> None:
    from bench.runner import RunConfig

    with pytest.raises(Exception, match="teacher|unknown generator profile"):
        RunConfig(profile="teacher-x-not-in-file")
