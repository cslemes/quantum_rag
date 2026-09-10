"""Graph state and its Pydantic entities. See data-model.md."""

from operator import add
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    """Verifiable requirement extracted by the planner. Becomes the critic's contract."""

    id: str
    kind: Literal["n_qubits", "gate_set", "property", "resource", "output_format"]
    description: str
    value: str | int | list[str] | None = None


class Chunk(BaseModel):
    doc_id: str
    text: str
    source: Literal["qiskit_api", "pennylane_api", "arxiv", "migration_guide"]
    library_version: str | None = None
    deprecated: bool = False  # FR-014: labeled, not omitted
    replacement: str | None = None  # what to use instead
    score: float


class ErrorRecord(BaseModel):
    iteration: int
    stage: Literal["static", "semantic", "resource"]
    error_type: str  # closed taxonomy — see data-model.md
    message: str  # truncated traceback or formatted diff
    payload: dict = Field(default_factory=dict)


class StaticResult(BaseModel):
    parsed: bool
    executed: bool
    transpiled: bool
    circuit_qpy: bytes | None = None
    error: ErrorRecord | None = None


class SemanticResult(BaseModel):
    # None whenever oracle_kind isn't "unitary" — a statevector-oracle circuit
    # can pass this check's target (see D3c, research.md) while still being
    # unitarily inequivalent (e.g. GHZ via a CX chain vs a CX star), so
    # `unitary_equiv=True` must never be inferred from `passed=True` alone.
    unitary_equiv: bool | None = None
    # None whenever oracle_kind isn't "statevector" (D3c) — the state-only
    # counterpart to unitary_equiv, for oracle_kind="unitary" this stays None
    # even when the check happens to pass.
    state_equiv: bool | None = None
    verification_method: Literal["exact", "composition", "statevector"] | None = None
    endianness_swapped: bool = False  # FR-005: its own category
    hellinger_fidelity: float | None = None
    hellinger_std: float | None = None  # deviation across seeds
    tvd: float | None = None
    energy_error: float | None = None
    passed: bool = False
    error: ErrorRecord | None = None


class ResourceResult(BaseModel):
    depth: int
    cx_count: int
    width: int
    depth_ratio: float  # generated / reference, SAME transpiler
    cx_ratio: float
    passed: bool


class CriticDecision(BaseModel):
    action: Literal["retry_retrieval", "retry_generation", "optimize", "abort", "done"]
    rationale: str
    retrieval_hint: str | None = None
    generation_hint: str | None = None


class AgentState(TypedDict, total=False):
    # input
    task_id: str
    spec: str
    oracle_ref: str
    coupling_map_name: str | None
    max_depth_ratio: float  # threaded from TaskSpec — see graph.py's resource_check

    # working — overwritten each iteration
    requirements: list[Requirement]
    chunks: list[Chunk]
    code: str
    iteration: int

    # current attempt's results
    static: StaticResult | None
    semantic: SemanticResult | None
    resource: ResourceResult | None
    decision: CriticDecision | None

    # accumulators
    error_history: Annotated[list[ErrorRecord], add]
    trace: Annotated[list[dict], add]

    # terminal
    status: Literal[
        "running",
        "success",
        "failed_semantic",
        "failed_static",
        "aborted",
        "infrastructure_error",
        "rejected_input",
    ]
