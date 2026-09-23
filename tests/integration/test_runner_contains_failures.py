"""One bad run must not destroy the suite (bug 11, follow-up).

The first live 360-run suite died on its first task: an exception escaped the
graph and took the process with it. Zero records were written, so three hours
of planned work produced a traceback and nothing else.

Containment is only half of it. The other half is that the record left behind
must be loud and must NOT be filed under `infrastructure_error` — that status
is excluded from the metrics denominator on the grounds that the world's
flakiness is not the generator's fault, and putting our own defects there
would hide them in the one bucket nothing is counted against.
"""

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from qiskit import QuantumCircuit, qpy

from bench.runner import EmptyIndexError, RunConfig, require_populated_index, run_suite
from bench.schema import RunRecord, TaskSpec
from qcagent.state import AgentState, StaticResult
from tests.integration.test_runner_blocks_unverified import _copy_task

LIB_VERSIONS = {"qiskit": "1.2.4", "ollama": "stub"}


@pytest.fixture
def tasks_dir(tmp_path: Path) -> Path:
    tasks, oracles = tmp_path / "tasks", tmp_path / "oracles"
    tasks.mkdir()
    oracles.mkdir()
    _copy_task("bell_phi_plus_2q", tasks, oracles)
    _copy_task("ghz_3q", tasks, oracles)
    return tasks


def test_an_exception_in_one_run_does_not_stop_the_others(tasks_dir: Path, tmp_path: Path) -> None:
    seen: list[str] = []

    def explodes_once(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        seen.append(task.task_id)
        if task.task_id == "bell_phi_plus_2q":
            raise RuntimeError("'Cannot apply instruction with classical bits: measure'")
        return {"status": "success", "iteration": 1, "code": "qc = None"}

    config = RunConfig(seeds=[1], tasks="all", results_dir=tmp_path / "results")
    jsonl = run_suite(
        config, task_runner=explodes_once, tasks_dir=tasks_dir, lib_versions=LIB_VERSIONS
    )

    assert len(seen) == 2, "the run after the exception must still have been attempted"
    records = [
        RunRecord.model_validate(json.loads(line)) for line in jsonl.read_text().splitlines()
    ]
    by_task = {r.task_id: r for r in records}

    assert by_task["ghz_3q"].status == "success"
    assert by_task["bell_phi_plus_2q"].status == "harness_error"


def test_the_harness_error_record_keeps_the_traceback(tasks_dir: Path, tmp_path: Path) -> None:
    """The record is the only evidence the defect happened — a status with no
    traceback would tell a reader that something broke and nothing about
    what, which is not enough to fix it after a three-hour unattended run."""

    def explodes(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        raise RuntimeError("classical bits: measure")

    config = RunConfig(seeds=[1], tasks=["ghz_3q"], results_dir=tmp_path / "results")
    jsonl = run_suite(config, task_runner=explodes, tasks_dir=tasks_dir, lib_versions=LIB_VERSIONS)

    record = RunRecord.model_validate(json.loads(jsonl.read_text().splitlines()[0]))
    assert record.status == "harness_error"
    (error,) = record.error_history
    assert error["stage"] == "harness"
    assert error["error_type"] == "RuntimeError"
    assert "classical bits: measure" in error["message"]
    assert "Traceback" in error["message"], "the traceback itself, not just the exception text"


def test_harness_errors_are_not_filed_as_infrastructure_errors(
    tasks_dir: Path, tmp_path: Path
) -> None:
    from analysis.metrics import compute, render

    def explodes(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        raise RuntimeError("boom")

    config = RunConfig(seeds=[1], tasks=["ghz_3q"], results_dir=tmp_path / "results")
    run_suite(config, task_runner=explodes, tasks_dir=tasks_dir, lib_versions=LIB_VERSIONS)

    from bench.runner import iter_records

    metrics = compute(iter_records(config.results_dir.glob("*/runs.jsonl").__next__()))

    assert metrics.harness_errors == 1
    assert metrics.infrastructure_errors == 0, "our bug is not the world's flakiness"
    assert metrics.infrastructure_error_rate == 0.0

    report = render(metrics)
    banner = report.splitlines()[0]
    assert "HARNESS ERROR" in banner, "the warning must precede any rate a reader could quote"
    assert "NOT a clean baseline" in report


def test_keyboard_interrupt_is_not_swallowed_as_a_defect(tasks_dir: Path, tmp_path: Path) -> None:
    """Someone pressing Ctrl-C is not a bug to record 360 times."""

    def interrupted(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        raise KeyboardInterrupt

    config = RunConfig(seeds=[1], tasks=["ghz_3q"], results_dir=tmp_path / "results")
    with pytest.raises(KeyboardInterrupt):
        run_suite(config, task_runner=interrupted, tasks_dir=tasks_dir, lib_versions=LIB_VERSIONS)


class _FakeQdrant:
    """Only the two methods the preflight uses."""

    def __init__(self, *, exists: bool, points: int) -> None:
        self._exists, self._points = exists, points

    def collection_exists(self, name: str) -> bool:
        return self._exists

    def count(self, name: str, exact: bool = True):
        return SimpleNamespace(count=self._points)


def test_suite_refuses_to_start_without_an_index() -> None:
    with pytest.raises(EmptyIndexError, match="does not exist"):
        require_populated_index(_FakeQdrant(exists=False, points=0))


def test_an_empty_collection_counts_as_no_index() -> None:
    """The dangerous case: the collection exists, so `search()` happily
    returns nothing and the suite measures a generator with no retrieval —
    a different system from the one under test, reported under its name."""
    with pytest.raises(EmptyIndexError, match="EMPTY"):
        require_populated_index(_FakeQdrant(exists=True, points=0))


def test_a_populated_index_is_accepted() -> None:
    require_populated_index(_FakeQdrant(exists=True, points=1020))


def test_a_transpiled_circuit_is_recorded_without_its_qpy_bytes(
    tasks_dir: Path, tmp_path: Path
) -> None:
    """Bug 14. `StaticResult.circuit_qpy` holds raw QPY; pydantic's JSON mode
    decodes bytes as UTF-8 and raises on the first non-text byte. No smoke
    run reached this, because a run only carries QPY once its code actually
    transpiles — so the suite died seven minutes in, on the first task that
    got that far.
    """
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    buffer = io.BytesIO()
    qpy.dump(qc, buffer)
    qpy_bytes = buffer.getvalue()
    assert b"\xff" in qpy_bytes or any(b > 127 for b in qpy_bytes), "needs non-UTF-8 bytes to bind"

    def transpiles(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        return {
            "status": "success",
            "iteration": 1,
            "code": "qc = QuantumCircuit(2)",
            "static": StaticResult(
                parsed=True, executed=True, transpiled=True, circuit_qpy=qpy_bytes
            ),
        }

    config = RunConfig(seeds=[1], tasks=["ghz_3q"], results_dir=tmp_path / "results")
    jsonl = run_suite(
        config, task_runner=transpiles, tasks_dir=tasks_dir, lib_versions=LIB_VERSIONS
    )

    record = RunRecord.model_validate(json.loads(jsonl.read_text().splitlines()[0]))
    assert record.status == "success", "a recordable run must not be downgraded"
    assert record.static is not None
    assert record.static["transpiled"] is True
    assert "circuit_qpy" not in record.static, "the binary must not reach the results file"


def test_a_record_that_cannot_be_serialized_costs_one_run_not_the_suite(
    tasks_dir: Path, tmp_path: Path
) -> None:
    """The first containment wrapped only the graph call, and the suite died
    anyway — in `_record`. Surviving the graph is not enough; the result has
    to survive being written down."""

    class Unserializable(BaseModel):
        model_config = {"arbitrary_types_allowed": True}
        boom: object = object()

    def returns_unserializable(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        return {"status": "success", "iteration": 1, "code": "", "static": Unserializable()}

    config = RunConfig(seeds=[1, 2], tasks=["ghz_3q"], results_dir=tmp_path / "results")
    jsonl = run_suite(
        config, task_runner=returns_unserializable, tasks_dir=tasks_dir, lib_versions=LIB_VERSIONS
    )

    lines = [line for line in jsonl.read_text().splitlines() if line.strip()]
    assert len(lines) == 2, "both seeds must still have produced a record"
    for line in lines:
        record = RunRecord.model_validate(json.loads(line))
        assert record.status == "harness_error"
        assert "Traceback" in record.error_history[0]["message"]
