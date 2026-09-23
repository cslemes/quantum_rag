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


def _report_payload(state: dict) -> dict | None:
    """The guarantee report as data for the client.

    `functional_correctness_verified` is passed through from the report
    object and never recomputed here. It is decided in exactly one place
    (report.py) and everything else reads it — the invariant F8/F10 cost this
    project two bugs to establish, and a UI that re-derived it would be the
    third.
    """
    report = state.get("guarantee_report")
    if report is None:
        return None
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
        health["ollama"] = f"unreachable: {exc}"
    return health
