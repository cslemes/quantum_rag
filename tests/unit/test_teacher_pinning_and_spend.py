"""The teacher is one model at one effort for the whole dataset; spend is
measured per call against a labelled estimate. No network."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from qcagent.distill.families import QubitPermutations
from qcagent.distill.families.permutations import cycles
from qcagent.distill.gate import StatementRegistry
from qcagent.distill.listing import (
    SnapshotNotListed,
    accepted_served_models,
    effort_problems,
    listing_entry,
    rate_discrepancies,
    snapshot_facts,
)
from qcagent.distill.pilot import (
    DatasetVersionMismatch,
    SpendAuthorization,
    SpendNotAuthorized,
    identity_of,
    lock_dataset_identity,
    run_pilot,
)
from qcagent.distill.spend import (
    SpendExceeded,
    SpendGuard,
    cost_from_tokens,
    estimate_from_tokens,
    window_at,
)
from qcagent.llm.openai_compatible_client import OpenAICompatibleClient
from qcagent.llm.profiles import Profile, get_profile, is_dated_snapshot
from qcagent.validators.sandbox import WorkerPool

PROFILE_NAME = "teacher-deepseek-v4.1-flash-1017"
ENTRY = json.loads(
    (
        Path(__file__).parent / "data" / "openrouter_listing_deepseek_v4.1_flash_1017.json"
    ).read_text()
)
FACTS = snapshot_facts(ENTRY)  # a copy of the live listing entry as read 2026-10-24
SECRET = "sk-or-SECRET-VALUE-0123456789"


def _profile_dict(**over) -> dict:
    base = dict(
        name="teacher-x",
        label="t",
        client_type="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        model="vendor/model-1017",
        credential_env="OPENROUTER_API_KEY",
        role="teacher",
        provider_options={"enforce_distillable_text": True},
        reasoning_effort="high",
    )
    base.update(over)
    return base


# -- the pin -----------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    [
        "deepseek/deepseek-v4.1-flash",
        "deepseek/deepseek-v4.1-flash-latest",
        "deepseek/deepseek-v4.1-flash:free",
        "deepseek/deepseek-v4.1-flash:nitro",
        "deepseek/auto",
    ],
)
def test_a_floating_alias_cannot_be_a_teacher(model: str) -> None:
    assert not is_dated_snapshot(model)
    with pytest.raises(ValidationError, match="dated snapshot"):
        Profile.model_validate(_profile_dict(model=model))


def test_a_teacher_must_state_its_reasoning_effort() -> None:
    with pytest.raises(ValidationError, match="reasoning_effort"):
        Profile.model_validate(_profile_dict(reasoning_effort=None))


def test_the_shipped_teacher_profile_is_the_dated_snapshot_at_high_effort() -> None:
    profile = get_profile(PROFILE_NAME)
    assert profile.model == "deepseek/deepseek-v4.1-flash-1017"
    assert profile.reasoning_effort == "high" and profile.role == "teacher"
    assert profile.provider_options is not None
    assert profile.provider_options.enforce_distillable_text is True
    assert profile.pricing_usd_per_mtok is None  # the price is time-varying


# -- effort is identity ------------------------------------------------------


class _Server:
    def __init__(self, handler) -> None:
        self.handler = handler
        self.bodies: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        return self.handler(body)


def _completion(model: str, content: str = "x", cost: float | None = 0.001) -> dict:
    usage: dict = {"prompt_tokens": 100, "completion_tokens": 300}
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-1",
        "model": model,
        "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
        ],
        "usage": usage,
    }


def _client(profile: Profile, server: _Server, cache_dir: Path, **over) -> OpenAICompatibleClient:
    assert profile.provider_options is not None
    client = OpenAICompatibleClient(
        SECRET,
        profile.model,
        "https://openrouter.example/api/v1",
        temperature=profile.determinism.temperature,
        top_p=profile.determinism.top_p,
        provider_options=profile.provider_options.as_body(),
        reasoning_effort=over.pop("reasoning_effort", profile.reasoning_effort),
        max_tokens_headroom=profile.max_tokens_headroom,
    )
    client._http = httpx.Client(transport=httpx.MockTransport(server))
    client.cache_dir = cache_dir
    return client


def test_effort_is_sent_recorded_as_sent_and_part_of_the_cache_key(tmp_path: Path) -> None:
    profile = get_profile(PROFILE_NAME)
    server = _Server(lambda b: httpx.Response(200, json=_completion(profile.model)))
    high = _client(profile, server, tmp_path)
    response = high.generate(system="s", prompt="p", seed=1, max_tokens=100)
    assert server.bodies[0]["reasoning"] == {"effort": "high"}
    assert response.provenance["reasoning_sent"] == {"effort": "high"}
    assert server.bodies[0]["max_tokens"] == 100 + profile.max_tokens_headroom

    high.generate(system="s", prompt="p", seed=1, max_tokens=100)
    assert len(server.bodies) == 1 and high.last_call_cache_hit  # same effort: a hit
    low = _client(profile, server, tmp_path, reasoning_effort="low")
    low.generate(system="s", prompt="p", seed=1, max_tokens=100)
    assert len(server.bodies) == 2 and not low.last_call_cache_hit  # another effort: a miss


def test_a_dataset_refuses_a_different_effort_or_snapshot(tmp_path: Path) -> None:
    profile = get_profile(PROFILE_NAME)
    estimate = estimate_from_tokens(80, 900, 2100, now=datetime(2026, 10, 24, 12, tzinfo=UTC))
    lock_dataset_identity(tmp_path, identity_of(profile, FACTS), estimate, "pilot-v1", FACTS, [])
    lock_dataset_identity(tmp_path, identity_of(profile, FACTS), estimate, "pilot-v1", FACTS, [])
    lowered = profile.model_copy(update={"reasoning_effort": "low"})
    with pytest.raises(DatasetVersionMismatch, match="new dataset version"):
        lock_dataset_identity(
            tmp_path, identity_of(lowered, FACTS), estimate, "pilot-v1", FACTS, []
        )
    repointed = {**FACTS, "canonical_slug": "deepseek/deepseek-v4.1-flash-20261111"}
    with pytest.raises(DatasetVersionMismatch):  # same id, now resolving elsewhere
        lock_dataset_identity(
            tmp_path, identity_of(profile, repointed), estimate, "pilot-v1", repointed, []
        )


# -- the listing as evidence ---------------------------------------------------


def test_the_listing_confirms_the_snapshot_the_effort_and_the_stated_rates() -> None:
    assert FACTS["id"] == "deepseek/deepseek-v4.1-flash-1017"
    assert FACTS["canonical_slug"] == "deepseek/deepseek-v4.1-flash-20261017"
    assert accepted_served_models(FACTS) == {FACTS["id"], FACTS["canonical_slug"]}
    assert effort_problems(FACTS, "high") == []
    assert effort_problems(FACTS, "medium") != []  # not offered by this model
    assert rate_discrepancies(FACTS) == []


def test_a_different_peak_window_or_price_in_the_listing_is_reported() -> None:
    moved = json.loads(json.dumps(FACTS))
    for override in moved["listed_pricing"]["overrides"]:
        if override.get("utc_start") == 600:
            override["utc_start"] = 700
    assert any("peak windows" in p for p in rate_discrepancies(moved))
    repriced = json.loads(json.dumps(FACTS))
    repriced["listed_pricing"]["completion"] = "0.0000009"
    assert any("base price" in p for p in rate_discrepancies(repriced))


def test_a_model_id_missing_from_the_listing_is_an_error() -> None:
    assert listing_entry(FACTS["id"], lambda: [ENTRY])["canonical_slug"] == FACTS["canonical_slug"]
    with pytest.raises(SnapshotNotListed):
        listing_entry("deepseek/deepseek-v4.1-flash-9999", lambda: [ENTRY])


# -- price windows and the guard ----------------------------------------------


@pytest.mark.parametrize(
    "when,window",
    [
        (datetime(2026, 10, 26, 0, 59, tzinfo=UTC), "off-peak"),  # Monday
        (datetime(2026, 10, 26, 1, 0, tzinfo=UTC), "peak"),
        (datetime(2026, 10, 26, 3, 59, tzinfo=UTC), "peak"),
        (datetime(2026, 10, 26, 4, 0, tzinfo=UTC), "off-peak"),
        (datetime(2026, 10, 26, 5, 59, tzinfo=UTC), "off-peak"),
        (datetime(2026, 10, 26, 6, 0, tzinfo=UTC), "peak"),
        (datetime(2026, 10, 26, 9, 59, tzinfo=UTC), "peak"),
        (datetime(2026, 10, 26, 10, 0, tzinfo=UTC), "off-peak"),
        (datetime(2026, 10, 24, 2, 0, tzinfo=UTC), "off-peak"),  # Saturday: no peak
        (datetime(2026, 10, 25, 7, 0, tzinfo=UTC), "off-peak"),  # Sunday
    ],
)
def test_peak_windows_are_weekday_utc(when: datetime, window: str) -> None:
    assert window_at(when) == window


def test_the_estimate_is_labelled_with_the_window_it_was_taken_in() -> None:
    off = estimate_from_tokens(80, 900, 2100, now=datetime(2026, 10, 24, 12, tzinfo=UTC))
    peak = estimate_from_tokens(80, 900, 2100, now=datetime(2026, 10, 26, 2, tzinfo=UTC))
    assert (off.window, peak.window) == ("off-peak", "peak")
    assert off.rates_usd_per_mtok == (0.15, 0.60) and peak.rates_usd_per_mtok == (0.30, 1.20)
    assert peak.usd == pytest.approx(2 * off.usd, rel=1e-3)
    assert "operator-stated" in off.rates_source and "80 calls" in off.basis
    assert cost_from_tokens(1_000_000, 1_000_000, "peak") == pytest.approx(1.5)


def test_actual_cost_is_usage_cost_and_a_missing_cost_is_labelled_computed() -> None:
    guard = SpendGuard(estimate_usd=1.0)
    at = datetime(2026, 10, 26, 2, tzinfo=UTC)  # peak
    assert guard.add(reported_cost=0.05, input_tokens=1, output_tokens=1, at=at) == (
        0.05,
        "usage.cost",
    )
    usd, source = guard.add(reported_cost=None, input_tokens=1000, output_tokens=1000, at=at)
    assert source == "computed" and usd == pytest.approx(cost_from_tokens(1000, 1000, "peak"))
    report = guard.report()
    assert report["calls_priced_from_tokens"] == 1 and report["calls"] == 2
    assert set(report["actual_by_window_usd"]) == {"peak"}


def test_a_run_stops_when_actual_passes_three_times_the_estimate() -> None:
    guard = SpendGuard(estimate_usd=0.10)
    at = datetime(2026, 10, 24, 12, tzinfo=UTC)
    guard.add(reported_cost=0.29, input_tokens=0, output_tokens=0, at=at)  # under 0.30
    with pytest.raises(SpendExceeded, match="stopping to report"):
        guard.add(reported_cost=0.02, input_tokens=0, output_tokens=0, at=at)
    assert guard.report()["actual_usd"] == pytest.approx(0.31)  # the crossing call is counted


# -- the pilot run ------------------------------------------------------------


AUTH = SpendAuthorization(ceiling_usd=10.0, granted_by="test")


def _code_for(pi: list[int], *, wrong: bool = False) -> str:
    lines = ["from qiskit import QuantumCircuit", f"qc = QuantumCircuit({len(pi)})"]
    for cycle in cycles(pi):
        order = range(len(cycle) - 1) if wrong else range(len(cycle) - 2, -1, -1)
        lines += [f"qc.swap({cycle[j]}, {cycle[j + 1]})" for j in order]
    return "```python\n" + "\n".join(lines) + "\n```"


@pytest.fixture(scope="module")
def pool():
    with WorkerPool(size=2, recycle_after=50) as p:
        yield p


def _setup(
    tmp_path: Path,
    *,
    wrong_for: set[int] | None = None,
    served: str | None = None,
    cost: float | None = 0.001,
):
    profile = get_profile(PROFILE_NAME)
    family = QubitPermutations()
    registry = StatementRegistry(tmp_path / "registry.jsonl")
    registry.admit_family(family)
    by_statement = {family.statement(v): v for v in family.variations()}

    def handler(body: dict) -> httpx.Response:
        v = by_statement[body["messages"][1]["content"]]
        wrong = v.index in (wrong_for or set())
        return httpx.Response(
            200,
            json=_completion(served or profile.model, _code_for(v.params["pi"], wrong=wrong), cost),
        )

    server = _Server(handler)
    client = _client(profile, server, tmp_path / "cache")
    return profile, family, registry, server, client


def _run(tmp_path, pool, profile, family, registry, client, estimate_usd=1.0, authorization=AUTH):
    now = datetime(2026, 10, 24, 12, tzinfo=UTC)
    estimate = estimate_from_tokens(20, 900, 2100, now=now)
    return run_pilot(
        registry=registry,
        families=(family,),
        client=client,
        profile=profile,
        out_dir=tmp_path / "out",
        guard=SpendGuard(estimate_usd=estimate_usd),
        estimate=estimate,
        dataset_version="pilot-test",
        pool=pool,
        snapshot=FACTS,
        authorization=authorization,
        now=lambda: now,
    )


def test_a_pilot_run_labels_what_the_oracle_accepts_and_only_that(tmp_path, pool) -> None:
    profile, family, registry, server, client = _setup(tmp_path, wrong_for={3})
    summary = _run(tmp_path, pool, profile, family, registry, client)
    records = [json.loads(x) for x in (tmp_path / "out" / "records.jsonl").read_text().splitlines()]
    assert len(records) == 20 and summary["halted"] is None
    labelled = [r for r in records if r["label"] == "verified_against_oracle"]
    assert len(labelled) == 19
    wrong = next(r for r in records if r["label"] is None)
    assert wrong["acceptance"]["passed"] is False and wrong["static"]["executed"] is True
    first = records[0]
    assert first["teacher"]["reasoning_effort"] == "high"
    assert first["teacher"]["model"] == "deepseek/deepseek-v4.1-flash-1017"
    assert first["provenance"]["reasoning_sent"] == {"effort": "high"}
    assert first["cost"] == {"usd": 0.001, "source": "usage.cost", "window": "off-peak"}
    assert summary["spend"]["actual_usd"] == pytest.approx(0.02)
    assert all(b["provider"] == {"enforce_distillable_text": True} for b in server.bodies)
    assert SECRET not in json.dumps(records) and SECRET not in json.dumps(summary)


def test_a_resumed_run_spends_nothing_again(tmp_path, pool) -> None:
    profile, family, registry, server, client = _setup(tmp_path)
    _run(tmp_path, pool, profile, family, registry, client)
    before = len(server.bodies)
    _run(tmp_path, pool, profile, family, registry, client)
    assert len(server.bodies) == before == 20


def test_a_run_over_three_times_the_estimate_stops_after_writing_the_crossing_record(
    tmp_path, pool
) -> None:
    profile, family, registry, server, client = _setup(tmp_path, cost=0.05)
    summary = _run(tmp_path, pool, profile, family, registry, client, estimate_usd=0.01)
    records = (tmp_path / "out" / "records.jsonl").read_text().splitlines()
    assert len(records) == 1 and "stopping to report" in summary["halted"]
    assert summary["spend"]["actual_over_estimate"] == pytest.approx(5.0)


def test_the_canonical_slug_is_an_accepted_serving_name(tmp_path, pool) -> None:
    profile, family, registry, server, client = _setup(tmp_path, served=FACTS["canonical_slug"])
    summary = _run(tmp_path, pool, profile, family, registry, client)
    assert summary["halted"] is None and summary["outcomes"]["verified_against_oracle"] == 20


def test_a_repointed_snapshot_halts_the_run(tmp_path, pool) -> None:
    profile, family, registry, server, client = _setup(tmp_path, served="deepseek/other-model-9999")
    summary = _run(tmp_path, pool, profile, family, registry, client)
    records = (tmp_path / "out" / "records.jsonl").read_text().splitlines()
    assert len(records) == 1 and "two teachers" in summary["halted"]
    assert json.loads(records[0])["served_model_differs"] is True


def test_a_run_with_no_reported_cost_prices_from_tokens_and_says_so(tmp_path, pool) -> None:
    profile, family, registry, server, client = _setup(tmp_path, cost=None)
    summary = _run(tmp_path, pool, profile, family, registry, client)
    first = json.loads((tmp_path / "out" / "records.jsonl").read_text().splitlines()[0])
    assert first["cost"]["source"] == "computed"
    assert summary["spend"]["calls_priced_from_tokens"] == 20


# -- spend authorization is a positive gate -----------------------------------


def test_a_run_with_a_credential_and_no_authorization_does_not_spend(tmp_path, pool) -> None:
    profile, family, registry, server, client = _setup(tmp_path)
    with pytest.raises(SpendNotAuthorized, match="not permission to spend"):
        _run(tmp_path, pool, profile, family, registry, client, authorization=None)
    assert server.bodies == []  # not one request left the process


def test_an_authorization_below_the_guards_ceiling_does_not_spend(tmp_path, pool) -> None:
    profile, family, registry, server, client = _setup(tmp_path)
    small = SpendAuthorization(ceiling_usd=0.01, granted_by="test")
    with pytest.raises(SpendNotAuthorized, match="above the authorized"):
        _run(tmp_path, pool, profile, family, registry, client, authorization=small)
    assert server.bodies == []


def test_the_grant_is_recorded_in_the_dataset_meta(tmp_path, pool) -> None:
    profile, family, registry, server, client = _setup(tmp_path)
    _run(tmp_path, pool, profile, family, registry, client)
    meta = json.loads((tmp_path / "out" / "dataset_meta.json").read_text())
    assert meta["spend_authorization"] == {"ceiling_usd": 10.0, "granted_by": "test"}


def test_temperature_and_top_p_are_sent_and_are_part_of_the_identity(tmp_path) -> None:
    profile = get_profile(PROFILE_NAME)
    assert (profile.determinism.temperature, profile.determinism.top_p) == (1.0, 1.0)
    server = _Server(lambda b: httpx.Response(200, json=_completion(profile.model)))
    client = _client(profile, server, tmp_path)
    client.temperature, client.top_p = 1.0, 1.0
    client.generate(system="s", prompt="p", seed=1, max_tokens=10)
    assert (server.bodies[0]["temperature"], server.bodies[0]["top_p"]) == (1.0, 1.0)
    client.top_p = 0.9
    client.generate(system="s", prompt="p", seed=1, max_tokens=10)
    assert len(server.bodies) == 2  # another top_p is another teacher: a cache miss
    assert (
        identity_of(profile, FACTS).top_p == 1.0 and identity_of(profile, FACTS).temperature == 1.0
    )


def test_a_teacher_cannot_leave_sampling_to_the_provider() -> None:
    for determinism in (
        {"reset_strategy": "none", "temperature": None, "top_p": 1.0, "num_ctx": None},
        {"reset_strategy": "none", "temperature": 1.0, "top_p": None, "num_ctx": None},
    ):
        with pytest.raises(ValidationError, match="temperature and top_p"):
            Profile.model_validate(_profile_dict(determinism=determinism))


# -- an infrastructure fault is not a verdict on the teacher's answer -----------


class _TimingOutPool:
    """Stands in for the sandbox pool: every execution times out."""

    def __init__(self, real) -> None:
        self.real = real
        self.timeouts = True

    def submit(self, code: str, timeout: int = 60):
        if self.timeouts:
            from qcagent.validators.sandbox import SandboxResult

            return SandboxResult(
                ok=False,
                circuit_qpy=None,
                stdout="",
                stderr=f"timeout after {timeout}s",
                wall_time_s=0.0,
                exec_time_s=0.0,
            )
        return self.real.submit(code, timeout)


def test_a_sandbox_timeout_is_an_infrastructure_failure_and_is_checked_again_for_free(
    tmp_path, pool
) -> None:
    profile, family, registry, server, client = _setup(tmp_path)
    flaky = _TimingOutPool(pool)
    first = _run(tmp_path, flaky, profile, family, registry, client)
    records = [json.loads(x) for x in (tmp_path / "out" / "records.jsonl").read_text().splitlines()]
    assert {r["reject_reason"] for r in records} == {"infrastructure_failed:sandbox_timeout"}
    assert first["outcomes"] == {"infrastructure_failed:sandbox_timeout": 20}
    calls_before = len(server.bodies)

    flaky.timeouts = False  # the fault is fixed; the same statements are checked again
    second = _run(tmp_path, flaky, profile, family, registry, client)
    assert len(server.bodies) == calls_before  # answered from the cache: no new request
    latest = {}
    for line in (tmp_path / "out" / "records.jsonl").read_text().splitlines():
        r = json.loads(line)
        latest[r["statement_id"]] = r
    assert len(latest) == 20 and all(
        r["label"] == "verified_against_oracle" for r in latest.values()
    )
    retry = next(iter(latest.values()))
    assert retry["cost"]["source"] == "cache"
    assert retry["retry_of_infrastructure_failure"]["original_cost"]["source"] == "usage.cost"
    assert second["outcomes"] == {"verified_against_oracle": 20}
