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

from qcagent.report import GuaranteeReport
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
    return "assertion_check" if static.transpiled else "critic"


def route_after_assertion_check(state: AgentState) -> str:
    """T088 — US3. A violated or not-evaluable outcome routes straight to
    `critic` (`critic.py`'s `_latest_error_type`/`_is_repeated_not_evaluable`
    do the actual classification, not this function). Otherwise:
    `semantic_check` when `oracle_ref` is present (the regression-suite
    path, unchanged from v1's cascade); straight to `critic` when it's
    absent (the general product path). Deliberately NOT
    `"resource_check" if coupling_map_name else "critic"` here, even though
    that was the original sketch in tasks.md T088: `resource_check`
    (graph.py) unconditionally loads `oracle_ref` to get a reference
    circuit to diff depth/CX against, so it cannot run at all without one,
    regardless of `coupling_map_name`. In the no-`oracle_ref` path, whether
    the circuit respects a declared coupling map is reported directly from
    `static.transpiled` (report.py/US4), not by running `resource_check`.
    """
    outcomes = state.get("assertion_results") or []
    if any(o.passed is not True for o in outcomes):
        return "critic"
    return "semantic_check" if state.get("oracle_ref") else "critic"


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


def terminal_status(state: AgentState, report: GuaranteeReport) -> str:
    """The explicit failure/success status attached at a terminal action
    (FR-008's "corte em MAX_ITER com status de falha explícito").

    US4: `success` means SOMETHING REAL about functional correctness was
    verified and passed; a clean run that verified nothing terminates as
    `completed_unverified` instead. Whether anything was verified is
    decided in exactly one place, `GuaranteeReport.
    functional_correctness_verified` (a passed reference comparison, or
    every user-declared assertion — see its docstring for the veto order),
    and this function only reads it. That is what makes it true that
    `status` and the rendered verdict cannot disagree.

    data-model.md's AgentState.status distinguishes `failed_static` /
    `failed_semantic` from the generic `aborted`, but nothing in spec.md,
    plan.md, or data-model.md states the rule for choosing between them —
    this is a genuine gap this function fills: it reads the stage off the
    most recent ErrorRecord, which is exactly the information the
    qualitative error taxonomy (T064) needs to know where the loop got
    stuck. A resource-layer cutoff (ResourceExcess) has no matching
    `failed_resource` status in the schema, so it falls through to the
    generic `aborted`, and so does an abort with no error history at all.

    US3: `AssertionNotEvaluable` is checked BEFORE the stage-based mapping,
    not folded into it — it shares `stage="semantic"` with ordinary
    semantic failures (`AssertionViolated` included), but is genuinely
    different (a well-posed check that never resolved either way, not one
    that resolved to "wrong") and gets its own terminal status regardless
    of whether the abort came from the two-consecutive-occurrence rule
    (`critic.py::_is_repeated_not_evaluable`) or from exhausting MAX_ITER
    with a not-evaluable assertion as the last recorded error.
    """
    decision = state["decision"]
    assert decision is not None, "terminal_status requires critic to have run"
    if decision.action == "done":
        # The report is the single place "verified" is decided — including
        # the reference path, now that the report carries `semantic` — so
        # `status` reads it instead of re-deriving a second answer that
        # could drift. An earlier version checked `semantic.passed` here
        # separately while the report ignored `semantic`, and the two
        # disagreed on every passing regression-suite run.
        return "success" if report.functional_correctness_verified else "completed_unverified"
    error_history = state.get("error_history", [])
    if error_history:
        last = error_history[-1]
        if last.error_type == "AssertionNotEvaluable":
            return "assertion_not_evaluable"
        if last.stage in _STAGE_TO_STATUS:
            return _STAGE_TO_STATUS[last.stage]
    return "aborted"


def _build_guarantee_report(state: AgentState) -> GuaranteeReport:
    """T096 — US4. Assembles the report purely from already-computed
    results (`static`, `assertion_results`, `resource`, `coupling_map_name`)
    — no new checks run here. `topology_respected` is derived straight from
    `static.transpiled` (reference-free evidence, plan.md's round-2 item 2
    decision), not from `resource_check`, which requires `oracle_ref`
    unconditionally and may never have run at all in the product path.
    `hardware_note` stays None — US5 (hardware execution) is not
    implemented, and None here is accurate rather than a gap silently
    hidden (`render_guarantee_report` renders its absence gracefully).
    `requirements` comes from `assertion_check`'s T091 pass, which runs
    whether or not any assertion was declared.
    """
    static = state.get("static")
    coupling_map_name = state.get("coupling_map_name")
    topology_respected = (
        None if coupling_map_name is None else (static.transpiled if static is not None else None)
    )
    return GuaranteeReport(
        executed=static.executed if static is not None else False,
        transpiled=static.transpiled if static is not None else False,
        requirements=state.get("requirement_results") or [],
        assertions=state.get("assertion_results") or [],
        n_qubits_correction=state.get("n_qubits_correction"),
        reference=state.get("semantic"),
        coupling_map_name=coupling_map_name,
        topology_respected=topology_respected,
        resource=state.get("resource"),
        hardware_note=None,
    )


def finalize(state: AgentState) -> dict:
    report = _build_guarantee_report(state)

    # `AgentState.guarantee_report` is typed `Any` (state.py explains why:
    # a precise annotation is either a circular import or a runtime
    # `NameError` from LangGraph's `get_type_hints()`). `Any` means mypy
    # stops guarding the product's single most important structure, so the
    # guarantee is re-established HERE, at the one boundary where the value
    # enters the state, as a runtime check rather than as inherited debt.
    # This is not a redundant assertion about a line two statements up: it
    # is the type system's job being done by hand because the type system
    # was forced to give it up, and it fails loudly if a future edit ever
    # puts something else (a dict, a None, a partially-built stand-in) into
    # this key.
    if not isinstance(report, GuaranteeReport):  # pragma: no cover - guards a type hole
        raise TypeError(
            f"finalize must put a GuaranteeReport in AgentState['guarantee_report'], "
            f"got {type(report).__name__} — see state.py's note on why this field is "
            f"typed Any and must be validated here instead of by mypy"
        )

    return {"status": terminal_status(state, report), "guarantee_report": report}
