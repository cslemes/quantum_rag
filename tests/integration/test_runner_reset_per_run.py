"""The generator is reset before every (task, seed), not once per suite (F28).

Ollama's prompt/KV cache carries state between calls and changes the answer at
temperature 0, so a task's result depended on the task before it. The unit of
analysis is (task, seed); these tests pin that each one starts from the same
engine state.
"""

from pathlib import Path

from bench.runner import RunConfig, run_suite
from bench.schema import TaskSpec
from qcagent.state import AgentState
from tests.integration.test_runner_blocks_unverified import _copy_task

LIB_VERSIONS = {"qiskit": "1.2.4", "ollama": "stub"}


def _run(tmp_path: Path, *, reset_per_run: bool | None) -> list[str]:
    tasks, oracles = tmp_path / "tasks", tmp_path / "oracles"
    tasks.mkdir()
    oracles.mkdir()
    _copy_task("bell_phi_plus_2q", tasks, oracles)
    _copy_task("ghz_3q", tasks, oracles)
    events: list[str] = []

    def runner(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        events.append(f"run {task.task_id} {seed}")
        return {"status": "success", "iteration": 1, "code": ""}

    extra = {} if reset_per_run is None else {"reset_per_run": reset_per_run}
    config = RunConfig(seeds=[1, 2], tasks="all", results_dir=tmp_path / "results", **extra)
    run_suite(
        config,
        task_runner=runner,
        tasks_dir=tasks,
        lib_versions=LIB_VERSIONS,
        reset_state=lambda: events.append("reset"),
    )
    return events


def test_reset_precedes_every_run_by_default(tmp_path: Path) -> None:
    events = _run(tmp_path, reset_per_run=None)
    assert events == [
        "reset", "run bell_phi_plus_2q 1",
        "reset", "run bell_phi_plus_2q 2",
        "reset", "run ghz_3q 1",
        "reset", "run ghz_3q 2",
    ]  # fmt: skip


def test_reset_per_run_can_be_turned_off(tmp_path: Path) -> None:
    assert "reset" not in _run(tmp_path, reset_per_run=False)


def test_the_policy_is_part_of_the_run_id() -> None:
    """Two runs under different reset policies must never share a run_id —
    their per-task results are not comparable (F28)."""
    from qcagent.config import make_run_id

    on = RunConfig(reset_per_run=True).model_dump(mode="json")
    off = RunConfig(reset_per_run=False).model_dump(mode="json")
    assert make_run_id(on, sha="x") != make_run_id(off, sha="x")


def test_the_ollama_url_can_point_elsewhere_and_is_recorded() -> None:
    """The RunPod arm points Ollama at an SSH tunnel; the default stays the
    configured local server, and where generation ran goes in the record."""
    from qcagent.config import settings

    assert RunConfig().ollama_url == settings.ollama_base_url
    remote = RunConfig(ollama_base_url="http://localhost:11435", generator_host="runpod:RTX 4090")
    assert remote.ollama_url == "http://localhost:11435"
    assert remote.generator_host == "runpod:RTX 4090"
