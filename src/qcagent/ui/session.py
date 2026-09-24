"""One interface run, streamed as it happens (US6, FR-023).

Drives the SAME graph the suite drives, via `qcagent.live.build_live_graph`.
There is no second orchestration here and there must never be: a demo path
that diverges from the measured path misrepresents the system, which is the
one thing this interface exists not to do (F20).

Progress comes from LangGraph's own `.stream()`, reading the `trace` channel
the nodes already write. Nothing is instrumented for the UI's benefit — if
the display and the run could disagree, the display would eventually lie.

READ-ONLY with respect to `results/`: this module constructs no `RunRecord`
and writes no file. A run lives in memory for the session and is gone when
the process exits. That is a scope decision, not an oversight — the suite
owns the record of what the system does (Principle III), and an interface
that also wrote records would create a second, unversioned source of numbers.
"""

import queue
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from qcagent.config import settings
from qcagent.graph import recursion_limit_for
from qcagent.live import LiveServices, build_live_graph, initial_state

# The interface states its seed rather than inheriting one (F20). 1 is a suite
# seed, so what a user sees here is comparable to the recorded suite run for
# an equivalent task instead of being a third, incomparable regime.
UI_SEED = 1

# Node -> what the user is told is happening. The graph's node names are
# internal vocabulary; these are the words a reader can act on.
STAGE_LABELS = {
    "planner": "reading your description",
    "retriever": "looking up Qiskit documentation",
    "generator": "writing the circuit",
    "static_check": "running the code",
    "assertion_check": "checking your assertions",
    "semantic_check": "comparing against the reference",
    "resource_check": "checking depth and gate count",
    "critic": "deciding what to fix",
    "finalize": "writing the guarantee report",
}


@dataclass
class Event:
    """One thing worth telling the user about. `kind` drives rendering."""

    kind: str  # stage | attempt_failed | done | error
    data: dict[str, Any] = field(default_factory=dict)


def _attempt_failures(state: dict) -> list[dict]:
    """The errors so far, as the user should read them: what was tried and why
    it did not work. This is the most informative thing on screen during a
    run that is going to fail, which is most runs."""
    out = []
    for err in state.get("error_history", []) or []:
        record = err if isinstance(err, dict) else err.model_dump()
        out.append(
            {
                "iteration": record.get("iteration"),
                "stage": record.get("stage"),
                "error_type": record.get("error_type"),
                "message": (record.get("message") or "").split("\n")[0][:300],
            }
        )
    return out


def run_streaming(
    services: LiveServices,
    *,
    spec: str,
    assertions_text: str | None,
    max_iter: int,
) -> Iterator[Event]:
    """Yields events while the graph runs. The graph executes on a worker
    thread because LangGraph's `.stream()` is synchronous and would otherwise
    block the event loop serving other requests.
    """
    events: queue.Queue[Event | None] = queue.Queue()

    def work() -> None:
        started = time.monotonic()
        try:
            graph = build_live_graph(services, seed=UI_SEED, max_iter=max_iter, oracle=None)
            state: dict = {}
            for update in graph.stream(
                initial_state(task_id="ui", spec=spec, assertions_text=assertions_text),
                config={"recursion_limit": recursion_limit_for(max_iter)},
                stream_mode="updates",
            ):
                for node, patch in update.items():
                    state.update(patch or {})
                    events.put(
                        Event(
                            "stage",
                            {
                                "node": node,
                                "label": STAGE_LABELS.get(node, node),
                                "attempt": state.get("iteration", 0),
                                "max_iter": max_iter,
                                "failures": _attempt_failures(state),
                                "elapsed_s": round(time.monotonic() - started, 1),
                            },
                        )
                    )
            events.put(
                Event(
                    "done",
                    {
                        "status": state.get("status"),
                        "code": state.get("code") or "",
                        "iterations": state.get("iteration", 0),
                        "max_iter": max_iter,
                        "failures": _attempt_failures(state),
                        "report": _report_payload(state),
                        "distribution": _distribution_payload(state),
                        "token": _remember_run(state),
                        "diagram": _diagram_payload(state),
                        "elapsed_s": round(time.monotonic() - started, 1),
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001 — surfaced to the user, never swallowed
            # Same reasoning as the runner's containment: our own defect is
            # reported as ours, not disguised as a failure of the request.
            events.put(Event("error", {"error_type": type(exc).__name__, "message": str(exc)}))
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()
    while (event := events.get()) is not None:
        yield event


# ---------------------------------------------------------------------------
# Checking a circuit that already exists, versus generating one
# ---------------------------------------------------------------------------
#
# These are DIFFERENT OPERATIONS and the interface had merged them. "Does this
# circuit satisfy X?" is a question about an artifact that exists; "generate a
# circuit satisfying X" is a request for one that does not. Declaring an
# assertion drafted from an observed distribution used to trigger the second
# when the user meant the first — and since the generator is unreliable, the
# new circuit routinely violated assertions drafted from the old one.
#
# So a finished run is kept by token, and checking evaluates against THAT
# stored circuit. Requirement: it must be unambiguous which circuit was
# verified, which is why the token is issued per run rather than "the last
# one" — "the last one" silently changes under a second browser tab.
#
# Bounded: this is a single-user demo surface (P2), not storage. Old entries
# fall off rather than accumulating.
_MAX_KEPT_RUNS = 8
_runs: "OrderedDict[str, dict]" = OrderedDict()


def _remember_run(state: dict) -> str | None:
    """Keeps a finished run's circuit so it can be checked without
    regenerating. Returns the token, or None when there is no circuit."""
    static = state.get("static")
    if static is None or static.circuit_qpy is None:
        return None
    token = uuid.uuid4().hex[:12]
    _runs[token] = {"static": static, "code": state.get("code") or ""}
    while len(_runs) > _MAX_KEPT_RUNS:
        _runs.popitem(last=False)
    return token


def check_stored_circuit(token: str, assertions_text: str) -> dict:
    """Evaluate assertions against a circuit ALREADY generated — no LLM, no
    regeneration.

    A check that passes IS functional verification of that circuit with
    respect to those assertions, so the guarantee report may legitimately say
    VERIFIED. What it must never be is ambiguous about WHICH circuit: the
    verdict here is about the stored QPY from the run identified by `token`,
    not about anything generated since.

    Reuses `_build_guarantee_report` rather than assembling a report here.
    The verdict is decided in one place and everything reads it (F8/F10); a
    second constructor would be the third instance of that bug.
    """
    from qcagent.nodes.routing import _build_guarantee_report
    from qcagent.validators.assertions import (
        AssertionParseError,
        evaluate_assertions,
        parse_assertions,
    )

    stored = _runs.get(token)
    if stored is None:
        return {"ok": False, "error": "that run is no longer held in memory — re-run it"}

    circuit = _circuit_from(stored["static"])
    if circuit is None:
        return {"ok": False, "error": "the stored run has no circuit to check"}

    try:
        parsed = parse_assertions(assertions_text, circuit.num_qubits)
    except AssertionParseError as exc:
        return {"ok": False, "error": str(exc)}
    if not parsed:
        return {"ok": False, "error": "no assertions to check"}

    outcomes = evaluate_assertions(parsed, circuit)
    report = _build_guarantee_report(
        {
            "static": stored["static"],
            "assertion_results": outcomes,
            "requirement_results": [],
            "coupling_map_name": None,
            "semantic": None,
            "resource": None,
            "n_qubits_correction": None,
        }
    )
    return {
        "ok": True,
        "token": token,
        "report": _serialise_report(report),
        "code": stored["code"],
    }


def _circuit_from(static: Any) -> Any:
    import io

    from qiskit import qpy

    if static.circuit_qpy is None:
        return None
    try:
        with io.BytesIO(static.circuit_qpy) as buffer:
            (circuit,) = qpy.load(buffer)
        return circuit
    except Exception:  # noqa: BLE001 — bug 21's class
        return None


def _diagram_payload(state: dict) -> dict | None:
    """The circuit drawn, from the QPY static_check already produced.

    Cosmetic by design: a failure here returns a reason and never raises. The
    diagram is the best-looking thing on the page and the least important —
    a verified run is still verified without it.
    """
    static = state.get("static")
    if static is None or static.circuit_qpy is None:
        return None
    circuit = _circuit_from(static)
    if circuit is None:
        return None
    from qcagent.ui.diagram import circuit_png

    data_uri, reason = circuit_png(circuit)
    return {"image": data_uri, "reason": reason}


def _distribution_payload(state: dict) -> dict | None:
    """What the circuit DOES (FR-018) — descriptive, never evaluative.

    Deliberately a sibling of the report rather than a field inside it. The
    guarantee report is the system's claim; the distribution is an
    observation, and merging them would let a reader take the observation as
    part of the claim. The client keeps them visually separate for the same
    reason (FR-017 in a new place).

    Reads the QPY that `static_check` already produced, so generated code is
    never executed a second time outside the sandbox.
    """
    static = state.get("static")
    if static is None or static.circuit_qpy is None:
        return None
    import io

    from qiskit import qpy

    from qcagent.validators.circuits import NotEvaluable
    from qcagent.validators.distribution import draft_assertion, outcome_distribution

    try:
        with io.BytesIO(static.circuit_qpy) as buffer:
            (circuit,) = qpy.load(buffer)
    except Exception:  # noqa: BLE001 — bug 21's class; never crash the run
        return None

    result = outcome_distribution(circuit)
    if isinstance(result, NotEvaluable):
        return {"available": False, "reason": result.reason}
    return {
        "available": True,
        "source": result.source,
        "n_qubits": result.n_qubits,
        "truncated": result.truncated,
        "total_outcomes": result.total_outcomes,
        "omitted_probability": result.omitted_probability,
        "outcomes": [
            {
                "bitstring": outcome.bitstring,
                "probability": outcome.probability,
                # The draft is built server-side, by the same code that can
                # check it, so the client never has to construct grammar.
                "draft": draft_assertion(outcome, n_qubits=result.n_qubits),
            }
            for outcome in result.outcomes
        ],
    }


def _report_payload(state: dict) -> dict | None:
    """The guarantee report as data for the client.

    `functional_correctness_verified` is passed through from the report
    object and never recomputed here. It is decided in exactly one place
    (report.py) and everything else reads it — the invariant F8/F10 cost this
    project two bugs to establish, and a UI that re-derived it would be the
    third.
    """
    report = state.get("guarantee_report")
    return None if report is None else _serialise_report(report)


def _serialise_report(report) -> dict:
    """One serialisation, used by both a generated run and a check of a
    stored circuit. Two would drift, and the thing they would drift about is
    the verdict."""
    from qcagent.report import render_guarantee_report

    return {
        "verified": report.functional_correctness_verified,
        "executed": report.executed,
        "transpiled": report.transpiled,
        "assertions": [
            {
                "text": _rendered(outcome.assertion),
                "passed": outcome.passed,  # True | False | None (not evaluable)
                "detail": outcome.detail,
            }
            for outcome in report.assertions
        ],
        "requirements": [
            # `r.requirement.description`, not `r.description`: a
            # RequirementOutcome WRAPS the Requirement rather than flattening
            # it, because the two have different provenance and the report
            # keeps them distinct. My unit tests used fabricated payloads and
            # missed this; the first real run through the container caught it
            # (F19, once more).
            {
                "description": r.requirement.description,
                "passed": r.passed,
                "detail": r.detail,
            }
            for r in report.requirements
        ],
        "text": render_guarantee_report(report),
    }


def _rendered(assertion: Any) -> str:
    from qcagent.validators.assertions import render_assertion

    return render_assertion(assertion)


def check_service_health() -> dict[str, str]:
    """Reports what the interface depends on, so a failure caused by a stopped
    container is not read as a failure of the system under test."""
    import httpx
    from qdrant_client import QdrantClient

    health = {}
    try:
        client = QdrantClient(url=settings.qdrant_url)
        from qcagent.retrieval.index import COLLECTION

        points = (
            client.count(COLLECTION, exact=True).count
            if client.collection_exists(COLLECTION)
            else 0
        )
        health["qdrant"] = f"{points} documents" if points else "EMPTY — run `make index`"
    except Exception as exc:  # noqa: BLE001
        health["qdrant"] = f"unreachable: {exc}"
    try:
        httpx.get(f"{settings.ollama_base_url}/api/version", timeout=3).raise_for_status()
        health["ollama"] = settings.ollama_model
    except Exception as exc:  # noqa: BLE001
        # Name the URL. "Connection refused" without it sends people to debug
        # the container when the usual cause is the SERVER: Ollama binds to
        # 127.0.0.1 by default, which a container cannot reach however
        # correctly it is configured.
        health["ollama"] = (
            f"unreachable at {settings.ollama_base_url} ({type(exc).__name__}). "
            "If Ollama runs on the host, it is probably bound to 127.0.0.1 — "
            "set OLLAMA_HOST=0.0.0.0 and restart it."
        )
    return health
