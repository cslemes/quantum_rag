"""T100 — MANDATORY (Principle IV, FR-028, SC-009).

One unverified reference must stop the WHOLE run, before any task executes.
Not "the broken task is skipped": a suite whose references aren't all
verified cannot produce a trustworthy number about any of them, and a
partially-run suite invites reading the tasks that did run as if they meant
something.

The runner's task execution is injected here, so the block is proven without
a sandbox, an LLM or a Qdrant: if the injected runner is ever called, the
block failed.
"""

import json
import shutil
from pathlib import Path

import pytest
from qiskit import QuantumCircuit, qpy

from bench.runner import (
    RunConfig,
    UnverifiedReferenceError,
    load_tasks,
    run_suite,
    verify_references,
)
from bench.schema import TaskSpec
from qcagent.state import AgentState

REPO_TASKS = Path("bench/tasks")


def _copy_task(task_id: str, tasks_dir: Path, oracles_dir: Path) -> TaskSpec:
    """Copies one real task + its oracle into a temporary tree, rewriting
    `oracle_path` so the copy is self-contained and the real oracle is never
    touched."""
    source = next(
        p for p in REPO_TASKS.rglob("*.json") if json.loads(p.read_text())["task_id"] == task_id
    )
    spec = json.loads(source.read_text())
    oracle_src = Path(spec["oracle_path"])
    oracle_dst = oracles_dir / oracle_src.name
    shutil.copy(oracle_src, oracle_dst)
    spec["oracle_path"] = str(oracle_dst)
    (tasks_dir / f"{task_id}.json").write_text(json.dumps(spec))
    return TaskSpec.model_validate(spec)


@pytest.fixture
def suite(tmp_path: Path) -> tuple[Path, TaskSpec, TaskSpec]:
    """A two-task suite: one sound task, one whose oracle will be corrupted."""
    tasks_dir, oracles_dir = tmp_path / "tasks", tmp_path / "oracles"
    tasks_dir.mkdir()
    oracles_dir.mkdir()
    sound = _copy_task("bell_phi_plus_2q", tasks_dir, oracles_dir)
    doomed = _copy_task("ghz_3q", tasks_dir, oracles_dir)
    return tasks_dir, sound, doomed


def _corrupt(task: TaskSpec) -> None:
    """Replaces the reference circuit with a different, wrong one — the
    oracle file stays valid QPY, so this tests the CHECKS, not the loader."""
    wrong = QuantumCircuit(task.n_qubits)
    wrong.x(0)
    with open(task.oracle_path, "wb") as f:
        qpy.dump(wrong, f)


def test_sound_suite_verifies_and_runs(suite, tmp_path: Path) -> None:
    tasks_dir, _, _ = suite
    calls: list[tuple[str, int]] = []

    def fake_runner(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        calls.append((task.task_id, seed))
        return {"status": "success", "iteration": 1, "code": "qc = None"}

    config = RunConfig(seeds=[1], tasks="all", results_dir=tmp_path / "results")
    jsonl = run_suite(
        config,
        task_runner=fake_runner,
        tasks_dir=tasks_dir,
        # Real runs ask the Ollama server for its version; an injected run has
        # no server, and the suite must not reach the network in tests.
        lib_versions={"qiskit": "1.2.4", "ollama": "stub"},
    )

    assert len(calls) == 2, "both tasks should have run"
    lines = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    assert {line["task_id"] for line in lines} == {"bell_phi_plus_2q", "ghz_3q"}
    assert all(line["status"] == "success" for line in lines)


def test_one_corrupted_reference_blocks_every_task(suite, tmp_path: Path) -> None:
    tasks_dir, _, doomed = suite
    _corrupt(doomed)

    def must_not_run(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        raise AssertionError(f"{task.task_id} ran despite an unverified reference in the run")

    config = RunConfig(seeds=[1], tasks="all", results_dir=tmp_path / "results")
    with pytest.raises(UnverifiedReferenceError) as excinfo:
        run_suite(config, task_runner=must_not_run, tasks_dir=tasks_dir)

    message = str(excinfo.value)
    assert "ghz_3q" in message
    assert "refusing to run any of the 2 configured task(s)" in message
    # Nothing was written: no results directory, so no partial run to misread.
    assert not (tmp_path / "results").exists()


def test_verify_references_names_every_failure_not_just_the_first(suite) -> None:
    tasks_dir, sound, doomed = suite
    _corrupt(sound)
    _corrupt(doomed)

    failures = verify_references(load_tasks(RunConfig(tasks="all"), tasks_dir))

    assert any("bell_phi_plus_2q" in f for f in failures)
    assert any("ghz_3q" in f for f in failures)


def test_unknown_task_id_is_an_error_not_a_smaller_suite(suite) -> None:
    tasks_dir, _, _ = suite
    with pytest.raises(ValueError, match="do not exist"):
        load_tasks(RunConfig(tasks=["bell_phi_plus_2q", "typo_task"]), tasks_dir)
