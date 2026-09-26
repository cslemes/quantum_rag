"""The protocol canary: seeds must be byte-identical before a suite runs.

The suite runs one seed because, under per-run reset, the three seeds of a task
were identical in every arm of T114 (F29). That identity is an invariant of the
protocol, so it is checked before every suite rather than paid for with 240
redundant runs. If contamination returns (F28) or the seed starts to matter,
the suite must refuse to run — and say where the seeds parted.
"""

import pytest

from bench.runner import ProtocolIntegrityError, RunConfig, run_suite, verify_protocol
from bench.schema import TaskSpec
from qcagent.state import AgentState
from tests.integration.test_runner_blocks_unverified import _copy_task

LIB_VERSIONS = {"qiskit": "1.2.4", "ollama": "stub"}


def _tasks_dir(tmp_path):
    tasks, oracles = tmp_path / "tasks", tmp_path / "oracles"
    tasks.mkdir()
    oracles.mkdir()
    _copy_task("ghz_3q", tasks, oracles)
    _copy_task("bell_phi_plus_2q", tasks, oracles)
    return tasks


def _state(code: str) -> AgentState:
    return {
        "status": "success",
        "iteration": 1,
        "code": code,
        "trace": [{"node": "planner", "requirements": []}, {"node": "generator", "code": code}],
    }


def _task(tmp_path) -> TaskSpec:
    from bench.runner import load_tasks

    return load_tasks(RunConfig(tasks=["ghz_3q"]), _tasks_dir(tmp_path))[0]


def test_identical_seeds_pass(tmp_path) -> None:
    def runner(task, seed, max_iter):
        return _state("qc = 1")

    assert verify_protocol(runner, [_task(tmp_path)], [1, 2, 3], 5, None) == []


def test_divergent_seeds_fail_and_name_where(tmp_path) -> None:
    def runner(task, seed, max_iter):
        return _state("qc = 1" if seed == 1 else "qc = 2")

    (failure, _) = verify_protocol(runner, [_task(tmp_path)], [1, 2, 3], 5, None)
    assert failure == "ghz_3q: seed 2 differs from seed 1 at trace step 1 (generator)"


def test_the_canary_resets_before_each_of_its_runs(tmp_path) -> None:
    events: list[str] = []

    def runner(task, seed, max_iter):
        events.append(f"run {seed}")
        return _state("qc = 1")

    verify_protocol(runner, [_task(tmp_path)], [1, 2], 5, lambda: events.append("reset"))
    assert events == ["reset", "run 1", "reset", "run 2"]


def test_a_failed_canary_refuses_the_suite_and_leaves_the_evidence(tmp_path) -> None:
    ran: list[int] = []

    def runner(task, seed, max_iter):
        ran.append(seed)
        return _state(f"qc = {seed}")

    config = RunConfig(
        seeds=[1],
        tasks=["bell_phi_plus_2q"],
        protocol_canary=["ghz_3q"],
        results_dir=tmp_path / "results",
    )
    with pytest.raises(ProtocolIntegrityError, match="seeds diverge"):
        run_suite(
            config,
            task_runner=runner,
            tasks_dir=_tasks_dir(tmp_path),
            lib_versions=LIB_VERSIONS,
            reset_state=lambda: None,
            check_protocol=True,
        )
    assert ran == [1, 2, 3], "only the canary ran; no suite task did"
    (evidence,) = (tmp_path / "results").glob("*/PROTOCOL_CHECK_FAILED.txt")
    assert "ghz_3q: seed 2 differs" in evidence.read_text()


def test_a_passed_canary_is_recorded_with_the_results(tmp_path) -> None:
    import json

    from bench.schema import RunRecord

    def runner(task, seed, max_iter):
        return _state("qc = 1")

    config = RunConfig(
        seeds=[1], tasks=["bell_phi_plus_2q"], protocol_canary=["ghz_3q"],
        results_dir=tmp_path / "results",
    )  # fmt: skip
    jsonl = run_suite(
        config,
        task_runner=runner,
        tasks_dir=_tasks_dir(tmp_path),
        lib_versions=LIB_VERSIONS,
        reset_state=lambda: None,
        check_protocol=True,
    )
    record = RunRecord.model_validate(json.loads(jsonl.read_text().splitlines()[0]))
    assert record.lib_versions["protocol_canary"].startswith("passed: 1 task(s) x 3 seeds")
