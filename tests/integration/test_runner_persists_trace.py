"""The run's trace reaches the results file (F27).

It used to be accumulated in AgentState and dropped by `_record`, so no stored
run could answer "what did retrieval return, and what did the critic ask
for?" — exactly the question F25 needed answered.
"""

import json
from pathlib import Path

from bench.runner import RunConfig, run_suite
from bench.schema import RunRecord, TaskSpec
from qcagent.state import AgentState
from tests.integration.test_runner_blocks_unverified import _copy_task

LIB_VERSIONS = {"qiskit": "1.2.4", "ollama": "stub"}


def _tasks_dir(tmp_path: Path) -> Path:
    tasks, oracles = tmp_path / "tasks", tmp_path / "oracles"
    tasks.mkdir()
    oracles.mkdir()
    _copy_task("ghz_3q", tasks, oracles)
    return tasks


def test_trace_is_persisted_with_hints_and_doc_ids(tmp_path: Path) -> None:
    trace = [
        {
            "node": "retriever",
            "queried": True,
            "query": "q",
            "n_chunks": 2,
            "doc_ids": ["HGate", "CXGate"],
        },
        {
            "node": "critic",
            "action": "retry_retrieval",
            "error_type": "HallucinatedSymbol",
            "rationale": "r",
            "retrieval_hint": "HGate",
            "generation_hint": None,
        },
    ]

    def runner(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        return {"status": "failed_static", "iteration": 1, "code": "", "trace": trace}

    config = RunConfig(seeds=[1], tasks=["ghz_3q"], results_dir=tmp_path / "results")
    jsonl = run_suite(
        config, task_runner=runner, tasks_dir=_tasks_dir(tmp_path), lib_versions=LIB_VERSIONS
    )

    record = RunRecord.model_validate(json.loads(jsonl.read_text().splitlines()[0]))
    assert record.trace == trace


def test_a_non_serializable_trace_value_does_not_cost_the_record(tmp_path: Path) -> None:
    """Bug 14's lesson: one unserializable value must not lose the whole run."""

    def runner(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        return {
            "status": "success",
            "iteration": 1,
            "code": "",
            "trace": [{"node": "x", "obj": object()}],
        }

    config = RunConfig(seeds=[1], tasks=["ghz_3q"], results_dir=tmp_path / "results")
    jsonl = run_suite(
        config, task_runner=runner, tasks_dir=_tasks_dir(tmp_path), lib_versions=LIB_VERSIONS
    )

    record = RunRecord.model_validate(json.loads(jsonl.read_text().splitlines()[0]))
    assert record.status == "success"
    assert record.trace[0]["obj"].startswith("<object object")


def test_records_written_before_the_field_existed_still_load() -> None:
    line = Path("results/ce9614fa3a6f60a6/runs.jsonl").read_text().splitlines()[0]
    assert RunRecord.model_validate(json.loads(line)).trace == []
