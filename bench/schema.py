"""Benchmark entities — T043. Normative source: data-model.md's "Entidades
do benchmark" section.

`bench/run_single.py` has carried a stand-in `TaskSpec` (only the fields that
dev tool used, no `Literal` constraint on `oracle_kind`) since before this
module existed — its own docstring says to delete it in favor of this import
once built, so that happens as part of this change too.
"""

from typing import Literal

from pydantic import BaseModel


class TaskSpec(BaseModel):
    task_id: str  # ex.: "t2_grover_3q_perturbed"
    tier: Literal["t1", "t2", "t3", "t4"]
    prompt: str
    n_qubits: int  # <= 20 geral; <= 13 se oracle_kind="unitary" (D3b/T052)
    # "resource" removido (D3h, research.md): nunca teve despacho em
    # make_semantic_check_node — resource_check é ortogonal a oracle_kind,
    # só precisa do circuito de referência que "statevector"/"unitary" já
    # fornecem. O que torna uma tarefa T4 é coupling_map não-nulo.
    oracle_kind: Literal["unitary", "statevector", "distribution", "energy"]
    oracle_path: str
    gate_set: list[str] | None = None
    coupling_map: str | None = None
    perturbed: bool = False
    perturbation_family: str | None = None
    base_task_id: str | None = None  # FR-017: pareamento canônica <-> perturbada
    tolerance: float = 0.99
    max_depth_ratio: float = 2.0


class RunRecord(BaseModel):
    """Uma linha do JSONL append-only (results/). Unidade de análise."""

    run_id: str
    task_id: str
    model_id: str
    seed: int
    # Mirrors AgentState.status (src/qcagent/state.py) — a value the graph can
    # terminate with but this Literal doesn't list would fail validation at
    # the moment of persistence, after the run's compute was already spent.
    # "success" means functional correctness was verified and passed;
    # "completed_unverified" means the run finished clean but nothing verified
    # it (US4). Metrics MUST NOT collapse the two — see data-model.md.
    # "assertion_not_evaluable" is reachable here for the same reason.
    status: Literal[
        "success",
        "completed_unverified",
        "failed_semantic",
        "failed_static",
        "aborted",
        "infrastructure_error",
        "rejected_input",
        "assertion_not_evaluable",
        # NOT produced by the graph: the runner writes this when a run raised
        # an unexpected exception, i.e. when WE have a bug (runner.py::
        # _run_one). Deliberately distinct from "infrastructure_error", which
        # is excluded from the metrics denominator — filing our own defects
        # under a status nothing counts against us is how a suite learns to
        # look healthy while being broken.
        "harness_error",
    ]
    iterations: int
    final_code: str
    static: dict | None
    semantic: dict | None
    resource: dict | None
    # T054/US4 — the rendered guarantee is part of the record, so a stored run
    # can be audited for what it claimed, not only for its status.
    guarantee_report: dict | None = None
    error_history: list[dict]
    # Per-node trace of the run (AgentState.trace): critic decisions with
    # rationale and hints, retrieval queries and the doc_ids returned. It used
    # to be accumulated and discarded, which made retrieval behaviour
    # undiagnosable after the fact (F27). Defaults to [] so records written
    # before this field existed still load.
    trace: list[dict] = []
    input_tokens: int
    output_tokens: int
    num_ctx: int | None = None  # D10b — valor efetivo, não o configurado
    cost_usd: float
    latency_s: float
    prefill_tok_s: float | None = None
    gen_tok_s: float | None = None
    gpu_memory_used_mib: int | None = None  # D10c
    gpu_processor: str | None = None  # ex.: "100% GPU" — detecta offload
    git_sha: str
    lib_versions: dict[str, str]
    timestamp: str
