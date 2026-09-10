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
    condition: Literal["C1", "C2", "C3", "C4", "C5"]
    seed: int
    status: Literal[
        "success",
        "failed_semantic",
        "failed_static",
        "aborted",
        "infrastructure_error",
        "rejected_input",
    ]
    iterations: int
    final_code: str
    static: dict | None
    semantic: dict | None
    resource: dict | None
    error_history: list[dict]
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
