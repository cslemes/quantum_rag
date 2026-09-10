"""Conditional edges for the graph (FR-008). See plan.md's ASCII diagram.

Two structural decisions fill gaps the diagram leaves implicit (it draws the
happy-path chain plus a single loop-back arrow, not full branch logic):

1. **Cascade short-circuit** — plan.md's Summary calls the four validation
   layers a "cascata determinística": each layer only runs if the previous
   one passed. `route_after_static`/`route_after_semantic` implement that:
   a failure skips straight to `critic` rather than running the next,
   meaningless layer (e.g. computing a depth ratio for a functionally wrong
   circuit).
2. **Single re-entry point** — the diagram draws exactly one loop-back arrow,
   into `retriever`, for every retry action (retry_retrieval,
   retry_generation, optimize). `route_after_critic` follows that literally:
   `retriever` is always the re-entry node, and it is `retriever`'s own job
   (T039) to skip an actual Qdrant round-trip when the action isn't
   retry_retrieval, rather than `routing.py` maintaining three separate
   loop-back edges.

A third case isn't in the diagram at all: `planner`, `generator`, and
`critic` each call an LLM and can come back with
`status="infrastructure_error"` (an exhausted-retry provider failure —
llm/base.py's `InfrastructureError`, T012b). That is not an `error_type` of
generated code, so every conditional-edge function below checks for it
FIRST and routes straight to the graph's end — it must never reach `critic`,
which would otherwise burn a retry iteration on an outage that has nothing
to do with the generated code.
"""

from qcagent.state import AgentState

_STAGE_TO_STATUS = {"static": "failed_static", "semantic": "failed_semantic"}


def route_after_planner(state: AgentState) -> str:
    """FR-030, FR-031, T024b: `rejected_input` skips retriever/generator/
    critic entirely. `planner` has already set `status` on the state — this
    function only chooses the graph edge."""
    status = state.get("status")
    if status == "infrastructure_error":
        return "infrastructure_error"
    if status == "rejected_input":
        return "rejected_input"
    return "retriever"


def route_after_generator(state: AgentState) -> str:
    if state.get("status") == "infrastructure_error":
        return "infrastructure_error"
    return "static_check"


def route_after_static(state: AgentState) -> str:
    static = state["static"]
    assert static is not None, "route_after_static requires static_check to have run"
    return "semantic_check" if static.transpiled else "critic"


def route_after_semantic(state: AgentState) -> str:
    semantic = state["semantic"]
    assert semantic is not None, "route_after_semantic requires semantic_check to have run"
    # verification_method is set only by the two circuit-vs-circuit checks
    # (check_with_endianness for oracle_kind="unitary", D3c's
    # check_statevector_with_endianness for oracle_kind="statevector") —
    # both leave a reference QuantumCircuit for resource_check to diff
    # against. It stays None for distributional/energy oracles, which have
    # no reference circuit at all (a counts dict / Hamiltonian instead), so
    # resource_check is skipped for those even when the oracle itself
    # passed. Deliberately NOT keyed on unitary_equiv (D3c): that field is
    # None for a statevector-oracle pass too, and a statevector oracle still
    # has a real reference circuit to compare resource usage against.
    if semantic.passed and semantic.verification_method is not None:
        return "resource_check"
    return "critic"


def route_after_critic(state: AgentState) -> str:
    if state.get("status") == "infrastructure_error":
        return "infrastructure_error"
    decision = state["decision"]
    assert decision is not None, "route_after_critic requires critic to have run"
    return "finalize" if decision.action in ("done", "abort") else "retriever"


def terminal_status(state: AgentState) -> str:
    """The explicit failure/success status attached at a terminal action
    (FR-008's "corte em MAX_ITER com status de falha explícito").

    data-model.md's AgentState.status distinguishes `failed_static` /
    `failed_semantic` from the generic `aborted`, but nothing in spec.md,
    plan.md, or data-model.md states the rule for choosing between them —
    this is a genuine gap this function fills: it reads the stage off the
    most recent ErrorRecord, which is exactly the information the
    qualitative error taxonomy (T064) needs to know where the loop got
    stuck. A resource-layer cutoff (ResourceExcess) has no matching
    `failed_resource` status in the schema, so it falls through to the
    generic `aborted`, and so does an abort with no error history at all.
    """
    decision = state["decision"]
    assert decision is not None, "terminal_status requires critic to have run"
    if decision.action == "done":
        return "success"
    error_history = state.get("error_history", [])
    if error_history:
        stage = error_history[-1].stage
        if stage in _STAGE_TO_STATUS:
            return _STAGE_TO_STATUS[stage]
    return "aborted"


def finalize(state: AgentState) -> dict:
    return {"status": terminal_status(state)}
