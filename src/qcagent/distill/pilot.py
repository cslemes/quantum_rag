"""The pilot generation run: registry ids in, verified-against-oracle records out.

One teacher, one sample per statement, checked against the family's declared
oracle. Everything that decides whether a run may continue is mechanical:

* statements come from the registry BY ID and only if they passed the gate;
* the teacher's identity (dated snapshot, reasoning effort, routing options) is
  written once to `dataset_meta.json`; a later run under a different identity is
  refused, because a mixed dataset has two teachers. Changing effort or snapshot
  starts a NEW dataset version in a new directory;
* the model that served each call must be the one requested (a snapshot that
  was repointed halts the run);
* a refusal is a statement's verdict and never retried without the flag; a run
  of refusals, a hard stop, or spend over the stop factor halts the run;
* nothing is spent twice: a statement with a record is skipped on resume.

The label on an accepted record is `verified_against_oracle`: the code ran, was
accepted by the family's strict/declared check against its oracle, and matched no
test reference. It is not "verified correct" and it says nothing of the model.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qiskit import qpy

from qcagent.distill.families import Family, Variation
from qcagent.distill.gate import StatementRegistry, circuit_leak_check
from qcagent.distill.listing import (
    accepted_served_models,
    effort_problems,
    rate_discrepancies,
)
from qcagent.distill.spend import Estimate, SpendExceeded, SpendGuard, window_at
from qcagent.distill.teacher import (
    PipelineHalt,
    RefusalBreaker,
    TeacherOutcome,
    call_teacher,
    require_teacher_client,
)
from qcagent.llm.base import BaseLLMClient
from qcagent.llm.profiles import Profile
from qcagent.nodes.generator import _extract_code
from qcagent.validators.sandbox import WorkerPool
from qcagent.validators.static import check_static

TEACHER_SYSTEM_PROMPT = """You write Qiskit 1.x Python code that builds a quantum \
circuit meeting the task statement.

Rules:
  - Assign the resulting QuantumCircuit to a variable named exactly `qc`.
  - Use only current, non-deprecated Qiskit 1.x API.
  - Follow the statement's qubit numbering and measurement instructions exactly.
  - Respond with a single fenced Python code block and nothing else.
"""
SEED = 1
MAX_TOKENS = 4096  # the profile's headroom is added on top for reasoning
LABEL = "verified_against_oracle"


class SpendNotAuthorized(RuntimeError):
    """A run that could spend money was started without an explicit authorization.
    A credential being present is not permission to spend."""


@dataclass(frozen=True)
class SpendAuthorization:
    """Created only by a caller that was told, in so many words, to spend: the
    script's `--authorize-spend` flag. `run_pilot` cannot be called without one,
    whatever credential or client it is given."""

    ceiling_usd: float
    granted_by: str  # where the grant came from, recorded in the dataset meta


class DatasetVersionMismatch(RuntimeError):
    """The teacher identity of this run differs from the dataset's."""


@dataclass(frozen=True)
class TeacherIdentity:
    profile: str
    model: str  # the dated snapshot id
    canonical_slug: str  # the dated release the id resolved to when the dataset began
    reasoning_effort: str
    provider_options: dict[str, Any]
    temperature: float  # sent explicitly: an unsent parameter is the provider's default
    top_p: float
    system_prompt_sha256: str
    seed: int
    max_tokens: int
    max_tokens_headroom: int


def identity_of(profile: Profile, facts: dict[str, Any]) -> TeacherIdentity:
    assert profile.reasoning_effort is not None and profile.provider_options is not None
    assert facts["id"] == profile.model
    return TeacherIdentity(
        profile=profile.name,
        model=profile.model,
        canonical_slug=facts["canonical_slug"],
        reasoning_effort=profile.reasoning_effort,
        provider_options=profile.provider_options.as_body(),
        temperature=profile.determinism.temperature,  # type: ignore[arg-type]
        top_p=profile.determinism.top_p,  # type: ignore[arg-type]
        system_prompt_sha256=hashlib.sha256(TEACHER_SYSTEM_PROMPT.encode()).hexdigest()[:16],
        seed=SEED,
        max_tokens=MAX_TOKENS,
        max_tokens_headroom=profile.max_tokens_headroom,
    )


def lock_dataset_identity(
    out_dir: Path,
    identity: TeacherIdentity,
    estimate: Estimate,
    dataset_version: str,
    facts: dict[str, Any],
    problems: list[str],
    authorization_record: dict[str, Any] | None = None,
) -> None:
    """Write the identity on first use; on every later use require it unchanged."""
    meta = out_dir / "dataset_meta.json"
    if meta.exists():
        recorded = json.loads(meta.read_text())
        if recorded["identity"] != asdict(identity):
            raise DatasetVersionMismatch(
                f"dataset {recorded['dataset_version']!r} was generated by "
                f"{recorded['identity']}; this run's teacher is {asdict(identity)}. "
                "A different snapshot, effort or routing is a new dataset version "
                "(a new directory), not a continuation."
            )
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    meta.write_text(
        json.dumps(
            {
                "dataset_version": dataset_version,
                "identity": asdict(identity),
                "first_estimate": asdict(estimate),
                "spend_authorization": authorization_record,
                "snapshot_facts": facts,
                "listing_discrepancies": problems,
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
            indent=2,
        )
        + "\n"
    )


INFRASTRUCTURE_PREFIX = "infrastructure_failed:"


def _latest_records(records: Path) -> dict[str, dict[str, Any]]:
    if not records.exists():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    for line in records.read_text().splitlines():
        if line:
            record = json.loads(line)
            latest[record["statement_id"]] = record
    return latest


def _is_infrastructure_failure(record: dict[str, Any]) -> bool:
    """A record whose check never reached the answer. Also recognises the older
    form (written before sandbox timeouts had their own reason code): a static
    failure whose message is the pool's timeout."""
    if str(record.get("reject_reason") or "").startswith(INFRASTRUCTURE_PREFIX):
        return True
    error = (record.get("static") or {}).get("error") or {}
    return "timeout after" in str(error.get("message") or "")


def _teacher_record(
    outcome: TeacherOutcome, *, family: Family, v: Variation, entry: dict, identity: TeacherIdentity
) -> dict[str, Any]:
    return {
        "statement_id": entry["id"],
        "statement": entry["statement"],
        "family": family.name,
        "oracle_kind": family.oracle_kind,
        "variation_key": v.key,
        "gate_version": entry["gate_version"],
        "teacher": asdict(identity),
        "state": outcome.state.value,
        "reason_code": outcome.reason_code,
        "detail": outcome.detail,
        "served_model_differs": outcome.served_model_differs,
        "from_cache": outcome.from_cache,
        "label": None,
        # Why an example was not labelled; None when it was. One code per cause.
        "reject_reason": None,
    }


def run_pilot(
    *,
    registry: StatementRegistry,
    families: tuple[Family, ...],
    client: BaseLLMClient,
    profile: Profile,
    out_dir: Path,
    guard: SpendGuard,
    estimate: Estimate,
    dataset_version: str,
    pool: WorkerPool,
    snapshot: dict[str, Any],
    authorization: SpendAuthorization | None,
    only_ids: set[str] | None = None,
    breaker: RefusalBreaker | None = None,
    now=lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Returns a summary. Raises nothing for a halt: the halt is recorded in the
    summary (and the records written so far are kept)."""
    if authorization is None:
        raise SpendNotAuthorized(
            "no spend authorization given; a credential present is not permission to spend"
        )
    if guard.ceiling_usd > authorization.ceiling_usd:
        raise SpendNotAuthorized(
            f"the guard's ceiling ${guard.ceiling_usd:.4f} is above the authorized "
            f"${authorization.ceiling_usd:.4f}"
        )
    require_teacher_client(client, profile)
    assert profile.reasoning_effort is not None
    problems = effort_problems(snapshot, profile.reasoning_effort)
    if problems:
        raise DatasetVersionMismatch(f"the pinned effort is not offered: {problems}")
    identity = identity_of(profile, snapshot)
    lock_dataset_identity(
        out_dir,
        identity,
        estimate,
        dataset_version,
        snapshot,
        rate_discrepancies(snapshot),
        asdict(authorization),
    )
    client.accepted_served_models = accepted_served_models(snapshot)  # type: ignore[attr-defined]
    breaker = breaker or RefusalBreaker()
    records = out_dir / "records.jsonl"
    latest = _latest_records(records)
    # A statement whose check hit an infrastructure fault (the sandbox timed out) is
    # not a verdict on the teacher's answer: it is checked again. The teacher call
    # is answered from the cache (the request is identical), so the retry costs
    # nothing and the original call's cost and tokens are carried on the new record.
    done = {sid for sid, r in latest.items() if not _is_infrastructure_failure(r)}
    by_name = {f.name: f for f in families}
    halted: str | None = None
    counts: dict[str, int] = {}

    with records.open("a") as sink:
        for entry in registry.entries():
            if entry["id"] in done or entry["verdict"] != "pass":
                continue
            if only_ids is not None and entry["id"] not in only_ids:
                continue
            registry.require_pass(entry["id"])  # by id, and the gate is still current
            family = by_name[entry["family"]]
            v = next(x for x in family.variations() if x.key == entry["variation_key"])
            outcome = call_teacher(
                client,
                statement_id=entry["id"],
                system=TEACHER_SYSTEM_PROMPT,
                prompt=entry["statement"],
                seed=SEED,
                max_tokens=MAX_TOKENS,
            )
            record = _teacher_record(outcome, family=family, v=v, entry=entry, identity=identity)
            earlier = latest.get(entry["id"])
            if earlier is not None:
                record["retry_of_infrastructure_failure"] = {
                    "original_cost": earlier.get("cost"),
                    "original_tokens": earlier.get("tokens"),
                    "original_recorded_reason": earlier["reject_reason"],
                }
            stop: Exception | None = None
            if outcome.response is not None:
                stop = _account(record, outcome, guard, now())
                _score(record, outcome, family, v, pool)
            # The record is written before any halt is raised: a paid call is
            # never lost to the stop that it triggered.
            sink.write(json.dumps(record) + "\n")
            sink.flush()
            key = LABEL if record["label"] else (record["reject_reason"] or record["state"])
            counts[key] = counts.get(key, 0) + 1
            try:
                if stop is not None:
                    raise stop
                breaker.record(outcome)
                if outcome.served_model_differs:
                    raise PipelineHalt(
                        f"the served model differs from the requested snapshot "
                        f"({client.model_id}); the dataset would hold two teachers"
                    )
            except (PipelineHalt, SpendExceeded) as exc:
                halted = str(exc)
                break
    summary = {
        "dataset_version": dataset_version,
        "teacher": asdict(identity),
        "outcomes": counts,
        "halted": halted,
        "spend": guard.report(),
        "estimate": asdict(estimate),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _account(
    record: dict[str, Any], outcome: TeacherOutcome, guard: SpendGuard, at: datetime
) -> SpendExceeded | None:
    """Put the call's cost on the record and the guard. `usage.cost` is the
    actual; a cache hit costs nothing now. Returns the exception to raise AFTER
    the record is written, if the stop factor was crossed."""
    response = outcome.response
    assert response is not None
    provenance = response.provenance or {}
    record["provenance"] = provenance
    record["response_text"] = response.text
    record["tokens"] = {"input": response.input_tokens, "output": response.output_tokens}
    if outcome.from_cache:
        record["cost"] = {"usd": 0.0, "source": "cache", "window": None}
        return None
    try:
        usd, source = guard.add(
            reported_cost=provenance.get("derived", {}).get("reported_cost"),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            at=at,
        )
        error = None
    except SpendExceeded as exc:
        error = exc
        usd, source = guard.last_usd, guard.last_source
    record["cost"] = {"usd": usd, "source": source, "window": window_at(at)}
    return error


def _score(
    record: dict[str, Any],
    outcome: TeacherOutcome,
    family: Family,
    v: Variation,
    pool: WorkerPool,
) -> None:
    assert outcome.response is not None
    code = _extract_code(outcome.response.text)
    record["code"] = code
    static = check_static(code, None, pool)
    record["static"] = {
        "parsed": static.parsed,
        "executed": static.executed,
        "transpiled": static.transpiled,
        "error": static.error.model_dump(mode="json") if static.error else None,
    }
    if not (static.executed and static.circuit_qpy):
        record["acceptance"] = None
        error = static.error.error_type if static.error else "no_circuit"
        message = static.error.message if static.error else ""
        if "timeout after" in message:
            # The sandbox timed out: the cascade labels it like any execution
            # failure, but it says nothing about the answer. Never counted as a
            # rejection; the statement is checked again on the next run.
            record["reject_reason"] = f"{INFRASTRUCTURE_PREFIX}sandbox_timeout"
        else:
            record["reject_reason"] = f"static_failed:{error}"
        return
    (circuit,) = qpy.load(io.BytesIO(static.circuit_qpy))
    check = family.accepts(v, circuit)
    record["acceptance"] = asdict(check)
    if not check.passed:
        record["reject_reason"] = f"rejected_by_oracle:{check.name}"
        return
    leak = circuit_leak_check(family.oracle_kind, circuit)
    record["leak_check"] = leak
    if leak["matches"]:
        record["reject_reason"] = "matches_test_reference:" + ",".join(leak["matches"])
    else:
        record["label"] = LABEL
