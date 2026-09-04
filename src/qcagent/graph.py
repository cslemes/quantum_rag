"""Graph assembly (T028, T029). See plan.md's ASCII diagram and node
contract table, and nodes/routing.py for the conditional-edge design notes.

`build_graph` wires together already-constructed node callables — it does
not itself know how to build an LLM client, a WorkerPool, or an oracle
loader. That construction is the caller's job (bench/runner.py in
production, tests/integration/test_us1_flow.py here), which keeps the graph
wiring testable without any live API key or Qdrant instance. What this
module DOES own is connecting the validators (`static.py`, `semantic.py`,
`resource.py` — already built and tested) into graph node functions, since
that adaptation is specific to how the graph carries state, not to the
validators themselves.

`recursion_limit_for` also lives here rather than in a caller: LangGraph's
default `recursion_limit` (25) counts graph *steps*, not agent iterations,
and the number of steps a single retry costs is a property of this graph's
own topology — every caller needs the same number, so it belongs where the
topology is defined, not re-derived per caller.
"""

import io
from collections.abc import Callable
from typing import Any, TypeAlias

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from qiskit import QuantumCircuit, qpy
from qiskit.quantum_info import SparsePauliOp

from qcagent.nodes.routing import (
    finalize,
    route_after_critic,
    route_after_generator,
    route_after_planner,
    route_after_semantic,
    route_after_static,
)
from qcagent.state import AgentState, ErrorRecord, SemanticResult
from qcagent.validators.resource import COUPLING_MAPS, check_resources
from qcagent.validators.sandbox import WorkerPool
from qcagent.validators.semantic import (
    MissingMeasurementError,
    ParameterBindingError,
    check_distribution,
    check_energy,
    check_with_endianness,
)
from qcagent.validators.static import check_static

# What a task's oracle resolves to: a circuit for the unitary path, a counts
# dict for the distributional path, or (Hamiltonian, exact_value) for VQE.
# How oracle_ref -> this object is bench/oracles' concern (Phase 5, T049),
# not built yet — the loader is injected so this module stays decoupled
# from that storage format.
Oracle: TypeAlias = QuantumCircuit | dict[str, int] | tuple[SparsePauliOp, float]
OracleLoader = Callable[[str], Oracle]


def _load_generated_circuit(state: AgentState) -> QuantumCircuit:
    """static_check already executed the code in the sandbox and produced
    QPY bytes (FR-025). semantic_check/resource_check deserialize THAT
    artifact rather than re-executing `state["code"]` — generated code is
    never exec'd a second time outside the sandbox.
    """
    static = state.get("static")
    if static is None or static.circuit_qpy is None:
        raise ValueError(
            "semantic/resource check requires a successfully transpiled circuit "
            "from static_check — route_after_static must not have reached here "
            "with transpiled=False"
        )
    with io.BytesIO(static.circuit_qpy) as buf:
        (qc,) = qpy.load(buf)
    return qc


def make_static_check_node(pool: WorkerPool) -> Callable[[AgentState], dict]:
    def static_check(state: AgentState) -> dict:
        coupling_map = COUPLING_MAPS[state.get("coupling_map_name") or "all_to_all"]
        result = check_static(state["code"], coupling_map, pool)

        error_history: list[ErrorRecord] = []
        if result.error is not None:
            # check_static hardcodes iteration=0 (it has no notion of the
            # agent's loop position) — patch the STORED result, not just a
            # separate copy for error_history, so `state["static"].error
            # .iteration` reflects the real attempt too (previously only the
            # error_history entry was patched, leaving the stored result
            # permanently reporting iteration=0).
            patched_error = result.error.model_copy(update={"iteration": state.get("iteration", 0)})
            result = result.model_copy(update={"error": patched_error})
            error_history.append(patched_error)

        return {
            "static": result,
            "error_history": error_history,
            "trace": [{"node": "static_check", "transpiled": result.transpiled}],
        }

    return static_check


def make_semantic_check_node(
    oracle_loader: OracleLoader, *, distribution_tolerance: float = 0.99
) -> Callable[[AgentState], dict]:
    def semantic_check(state: AgentState) -> dict:
        generated = _load_generated_circuit(state)
        oracle = oracle_loader(state["oracle_ref"])
        iteration = state.get("iteration", 0)

        if isinstance(oracle, QuantumCircuit):
            result = check_with_endianness(generated, oracle, n_qubits=generated.num_qubits)
            if result.error is not None:
                result = result.model_copy(
                    update={"error": result.error.model_copy(update={"iteration": iteration})}
                )
        elif isinstance(oracle, dict):
            result = _check_distribution_oracle(
                generated, oracle, iteration, distribution_tolerance
            )
        else:
            hamiltonian, exact_value = oracle
            result = _check_energy_oracle(generated, hamiltonian, exact_value, iteration)

        error_history = [result.error] if result.error is not None else []
        return {
            "semantic": result,
            "error_history": error_history,
            "trace": [{"node": "semantic_check", "passed": result.passed}],
        }

    return semantic_check


def _check_distribution_oracle(
    generated: QuantumCircuit, reference_counts: dict[str, int], iteration: int, tolerance: float
) -> SemanticResult:
    try:
        verdict = check_distribution(generated, reference_counts)
    except MissingMeasurementError as exc:
        # data-model.md's closed taxonomy files MissingMeasurement under
        # stage="static" even though it's caught here, in the semantic
        # layer's own pre-flight check — kept faithful to the documented
        # table rather than "corrected" to stage="semantic".
        return SemanticResult(
            passed=False,
            error=ErrorRecord(
                iteration=iteration,
                stage="static",
                error_type="MissingMeasurement",
                message=str(exc),
            ),
        )
    passed = verdict.hellinger_fidelity >= tolerance
    return SemanticResult(
        hellinger_fidelity=verdict.hellinger_fidelity,
        hellinger_std=verdict.hellinger_std,
        tvd=verdict.tvd,
        passed=passed,
        error=None
        if passed
        else ErrorRecord(
            iteration=iteration,
            stage="semantic",
            error_type="ConceptualAlgorithmError",
            message=f"hellinger_fidelity={verdict.hellinger_fidelity:.4f} < tolerância {tolerance}",
        ),
    )


def _check_energy_oracle(
    generated: QuantumCircuit, hamiltonian: SparsePauliOp, exact_value: float, iteration: int
) -> SemanticResult:
    try:
        verdict = check_energy(generated, hamiltonian, exact_value)
    except ParameterBindingError as exc:
        # Same note as MissingMeasurement above: stage="static" per the
        # closed taxonomy table, despite being caught in semantic_check.
        return SemanticResult(
            passed=False,
            error=ErrorRecord(
                iteration=iteration,
                stage="static",
                error_type="ParameterBindingError",
                message=str(exc),
            ),
        )
    return SemanticResult(
        energy_error=verdict.energy_error,
        passed=verdict.passed,
        error=None
        if verdict.passed
        else ErrorRecord(
            iteration=iteration,
            stage="semantic",
            error_type="ConceptualAlgorithmError",
            message=f"energy_error={verdict.energy_error:.4f} exceeds tolerance",
        ),
    )


def make_resource_check_node(
    oracle_loader: OracleLoader, *, opt_level: int = 2
) -> Callable[[AgentState], dict]:
    def resource_check(state: AgentState) -> dict:
        generated = _load_generated_circuit(state)
        oracle = oracle_loader(state["oracle_ref"])
        if not isinstance(oracle, QuantumCircuit):
            raise TypeError(
                "resource_check reached with a non-circuit oracle — "
                "route_after_semantic should only route here when unitary_equiv is not None"
            )

        coupling_map_name = state.get("coupling_map_name") or "all_to_all"
        result = check_resources(generated, oracle, coupling_map_name, opt_level=opt_level)

        # ResourceResult has no `.error` field (data-model.md) — the
        # ErrorRecord is built here rather than in resource.py, purely so
        # error_history (and terminal_status's stage lookup) stays accurate
        # even when a resource-only failure is the reason the loop cuts off.
        error_history: list[ErrorRecord] = []
        if not result.passed:
            error_history.append(
                ErrorRecord(
                    iteration=state.get("iteration", 0),
                    stage="resource",
                    error_type="ResourceExcess",
                    message=f"depth_ratio={result.depth_ratio:.2f}, cx_ratio={result.cx_ratio:.2f}",
                )
            )

        return {
            "resource": result,
            "error_history": error_history,
            "trace": [{"node": "resource_check", "passed": result.passed}],
        }

    return resource_check


def build_graph(
    *,
    planner_node: Callable[[AgentState], dict],
    retriever_node: Callable[[AgentState], dict],
    generator_node: Callable[[AgentState], dict],
    static_check_node: Callable[[AgentState], dict],
    semantic_check_node: Callable[[AgentState], dict],
    resource_check_node: Callable[[AgentState], dict],
    critic_node: Callable[[AgentState], dict],
    interrupt_before: list[str] | None = None,
    checkpointer: Any = None,
) -> CompiledStateGraph:
    """Assembles the StateGraph. `interrupt_before` (T029, FR-010) is `None`
    by default — pass `["resource_check"]` to pause after semantic_check has
    populated `semantic` but before resource_check runs, for optional human
    review. A real pause requires a `checkpointer` (e.g.
    `langgraph.checkpoint.memory.InMemorySaver()`) — without one, LangGraph
    has nowhere to persist the paused state and `interrupt_before` has no
    effect, which is also why it's harmless to leave both at their defaults
    in production until FR-010's human-review path is actually wired up.
    """
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("generator", generator_node)
    graph.add_node("static_check", static_check_node)
    graph.add_node("semantic_check", semantic_check_node)
    graph.add_node("resource_check", resource_check_node)
    graph.add_node("critic", critic_node)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {"retriever": "retriever", "rejected_input": END, "infrastructure_error": END},
    )
    graph.add_edge("retriever", "generator")
    graph.add_conditional_edges(
        "generator",
        route_after_generator,
        {"static_check": "static_check", "infrastructure_error": END},
    )
    graph.add_conditional_edges(
        "static_check", route_after_static, {"semantic_check": "semantic_check", "critic": "critic"}
    )
    graph.add_conditional_edges(
        "semantic_check",
        route_after_semantic,
        {"resource_check": "resource_check", "critic": "critic"},
    )
    graph.add_edge("resource_check", "critic")
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {"retriever": "retriever", "finalize": "finalize", "infrastructure_error": END},
    )
    graph.add_edge("finalize", END)

    return graph.compile(interrupt_before=interrupt_before, checkpointer=checkpointer)


# One retry iteration's worst-case path: retriever -> generator ->
# static_check -> semantic_check -> resource_check -> critic. Failing early
# (e.g. at static_check) costs fewer steps, but the limit has to cover the
# worst case, not the common one.
_NODES_PER_ITERATION = 6
# planner + finalize, plus headroom for LangGraph's own step bookkeeping —
# deliberately generous rather than exact, since undercounting turns into a
# GraphRecursionError mid-experiment instead of a clean terminal status.
_GRAPH_OVERHEAD_STEPS = 10


def recursion_limit_for(max_iter: int) -> int:
    """The `config={"recursion_limit": ...}` every caller of
    `compiled_graph.invoke()`/`.stream()` MUST pass — LangGraph's default of
    25 is invoke-time, not something `build_graph`/`compile()` can set once
    on the caller's behalf, and it silently caps out well before a run with
    several retries at the default `MAX_ITER=5` finishes (confirmed: a
    resource_check-cascade retry loop needs 6 steps/iteration, so 5 retries
    alone can need 30+ steps against a 25-step default).
    """
    return max_iter * _NODES_PER_ITERATION + _GRAPH_OVERHEAD_STEPS
