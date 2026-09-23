"""T103 — the three US7 acceptance scenarios (spec.md), end to end through
the real runner, metrics and comparison. Task execution is injected (the
suite's own guarantees are about recording and comparing runs, not about
what a live Ollama answers), but everything else is real: reference
verification, JSONL persistence, metrics, per-task comparison.
"""

import json
from pathlib import Path

import pytest

from analysis.compare import compare
from analysis.metrics import compute
from bench.runner import RunConfig, UnverifiedReferenceError, iter_records, run_suite
from bench.schema import TaskSpec
from qcagent.state import AgentState
from tests.integration.test_runner_blocks_unverified import _copy_task, _corrupt

_LIB_VERSIONS = {"qiskit": "1.2.4", "ollama": "stub"}


@pytest.fixture
def two_task_suite(tmp_path: Path) -> Path:
    tasks_dir, oracles_dir = tmp_path / "tasks", tmp_path / "oracles"
    tasks_dir.mkdir()
    oracles_dir.mkdir()
    _copy_task("bell_phi_plus_2q", tasks_dir, oracles_dir)
    _copy_task("ghz_3q", tasks_dir, oracles_dir)
    return tasks_dir


def _runner(outcomes: dict[str, str]):
    def run(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        return {"status": outcomes[task.task_id], "iteration": 1, "code": "qc = None"}

    return run


def test_scenario1_suite_produces_success_rate_per_tier_with_provenance(
    two_task_suite: Path, tmp_path: Path
) -> None:
    """Given the suite, when executed, then it produces a success rate by
    tier with run_id, seeds and versions recorded."""
    config = RunConfig(seeds=[1, 2], tasks="all", results_dir=tmp_path / "results")
    jsonl = run_suite(
        config,
        task_runner=_runner({"bell_phi_plus_2q": "success", "ghz_3q": "failed_semantic"}),
        tasks_dir=two_task_suite,
        lib_versions=_LIB_VERSIONS,
    )

    records = list(iter_records(jsonl))
    assert len(records) == 4, "one record per (task, seed)"
    assert {r.seed for r in records} == {1, 2}
    assert len({r.run_id for r in records}) == 1
    assert all(r.lib_versions == _LIB_VERSIONS and r.git_sha for r in records)
    # The configuration that produced the run is stored beside it.
    assert (jsonl.parent / "config.yaml").exists()

    metrics = compute(records, {"bell_phi_plus_2q": "t1", "ghz_3q": "t1"})
    assert metrics.success_rate == 0.5
    assert metrics.success_rate_by_tier == {"t1": 0.5}


def test_scenario2_two_runs_are_comparable_per_task(two_task_suite: Path, tmp_path: Path) -> None:
    """Given two runs of the suite, when compared, then the differences are
    identifiable per task."""
    first = run_suite(
        RunConfig(seeds=[1], tasks="all", results_dir=tmp_path / "before"),
        task_runner=_runner({"bell_phi_plus_2q": "success", "ghz_3q": "success"}),
        tasks_dir=two_task_suite,
        lib_versions=_LIB_VERSIONS,
    )
    second = run_suite(
        RunConfig(seeds=[1], tasks="all", results_dir=tmp_path / "after"),
        task_runner=_runner({"bell_phi_plus_2q": "success", "ghz_3q": "failed_semantic"}),
        tasks_dir=two_task_suite,
        lib_versions=_LIB_VERSIONS,
    )

    result = compare(iter_records(first), iter_records(second))
    assert [c.task_id for c in result.regressed] == ["ghz_3q"]
    assert result.divergence_rate == 0.5


def test_scenario3_unverified_reference_blocks_the_run(
    two_task_suite: Path, tmp_path: Path
) -> None:
    """Given a reference of the suite, when the validation process runs,
    then unverified references block execution."""
    doomed = TaskSpec.model_validate(json.loads((two_task_suite / "ghz_3q.json").read_text()))
    _corrupt(doomed)

    with pytest.raises(UnverifiedReferenceError):
        run_suite(
            RunConfig(seeds=[1], tasks="all", results_dir=tmp_path / "results"),
            task_runner=_runner({"bell_phi_plus_2q": "success", "ghz_3q": "success"}),
            tasks_dir=two_task_suite,
            lib_versions=_LIB_VERSIONS,
        )
    assert not (tmp_path / "results").exists()


def test_a_later_run_can_never_rewrite_an_earlier_one(two_task_suite: Path, tmp_path: Path) -> None:
    """Principle III: `run_id` is hash(config + git sha + timestamp), so each
    run gets its own directory and its own append-only file. A second run
    cannot touch what the first recorded, even with an identical config."""
    config = RunConfig(seeds=[1], tasks=["bell_phi_plus_2q"], results_dir=tmp_path / "results")
    runner = _runner({"bell_phi_plus_2q": "success"})

    first = run_suite(
        config, task_runner=runner, tasks_dir=two_task_suite, lib_versions=_LIB_VERSIONS
    )
    first_bytes = first.read_bytes()
    second = run_suite(
        config, task_runner=runner, tasks_dir=two_task_suite, lib_versions=_LIB_VERSIONS
    )

    assert second != first, "each run records into its own run_id directory"
    assert first.read_bytes() == first_bytes, "the earlier run's records are untouched"
    assert len(list(iter_records(first))) == len(list(iter_records(second))) == 1


def test_records_within_a_run_are_appended_not_overwritten(
    two_task_suite: Path, tmp_path: Path
) -> None:
    config = RunConfig(seeds=[1, 2, 3], tasks="all", results_dir=tmp_path / "results")
    jsonl = run_suite(
        config,
        task_runner=_runner({"bell_phi_plus_2q": "success", "ghz_3q": "aborted"}),
        tasks_dir=two_task_suite,
        lib_versions=_LIB_VERSIONS,
    )
    records = list(iter_records(jsonl))
    assert len(records) == 6, "2 tasks x 3 seeds, every one kept"
