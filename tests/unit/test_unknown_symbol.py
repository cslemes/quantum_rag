"""UnknownSymbol: negative knowledge derived from the runtime (T113, F25, F26).

104 of the 112 baseline runs that ended on an ImportError named a symbol that
never existed. Retrieval had no correction to offer — documentation describes
what exists — and the same symbol recurred in 58-68% of transitions. These
tests pin the correction that replaces it: derived from the INSTALLED Qiskit,
deterministic, with no LLM in the loop.
"""

import pytest

from qcagent.nodes.critic import make_critic_node, route_action
from qcagent.validators.static import (
    _classify_sandbox_failure,
    _importable_symbols,
    symbol_correction_for,
)
from tests.unit.test_missing_import_routing import _ExplodingLLM, _state


def _import_error(symbol: str, module: str = "qiskit.circuit.library") -> str:
    return f"ImportError: cannot import name '{symbol}' from '{module}' (/venv/qiskit/__init__.py)"


@pytest.mark.parametrize(
    ("symbol", "replacement"),
    [
        # PennyLane operation names (F26) — no spelling overlap with Qiskit's
        ("CNOT", "CXGate"),
        ("Hadamard", "HGate"),
        ("PauliZ", "ZGate"),
        # PennyLane name + Qiskit's suffix
        ("CNOTGate", "CXGate"),
        ("HadamardGate", "HGate"),
        # the `Gate` suffix omitted
        ("H", "HGate"),
        ("RZ", "RZGate"),
        # case and underscores (2.x function names the corpus once taught, F24)
        ("efficient_su2", "EfficientSU2"),
        ("GraphStateGate", "GraphState"),
    ],
)
def test_the_intended_symbol_is_named(symbol: str, replacement: str) -> None:
    fix = symbol_correction_for(_import_error(symbol))
    assert fix is not None
    assert fix.replacement == replacement
    assert fix.import_line == f"from qiskit.circuit.library import {replacement}"
    assert _classify_sandbox_failure(_import_error(symbol)) == "UnknownSymbol"


def test_a_real_symbol_from_the_wrong_module_gets_the_right_module() -> None:
    fix = symbol_correction_for(_import_error("SparsePauliOp"))
    assert fix is not None
    assert fix.import_line == "from qiskit.quantum_info import SparsePauliOp"
    assert "it is in `qiskit.quantum_info`" in fix.reason


@pytest.mark.parametrize("symbol", ["PhaseExp", "HamiltonianVariationalAnsatz", "PauliSumOp"])
def test_no_neighbour_stays_a_hallucination(symbol: str) -> None:
    """No real symbol is near these; retrieval stays the action, as before."""
    assert symbol_correction_for(_import_error(symbol)) is None
    assert _classify_sandbox_failure(_import_error(symbol)) == "HallucinatedSymbol"


def test_submodules_are_never_offered_as_symbols() -> None:
    """`grover_operator` is a submodule in 1.2.4 and a function in 2.x — the
    corpus-taught error of F24. An index that offered it would recreate it."""
    assert "grover_operator" not in _importable_symbols()
    assert "phase_estimation" not in _importable_symbols()


def test_routes_to_generation_with_the_exact_line_and_no_llm_call() -> None:
    state = _state(_import_error("H"))
    action, error_type = route_action(state["static"], None, None, None, 1, 5, [])
    assert (action, error_type) == ("retry_generation", "UnknownSymbol")

    decision = make_critic_node(_ExplodingLLM(), max_iter=5, seed=1)(state)["decision"]
    assert "from qiskit.circuit.library import HGate" in decision.generation_hint
    assert "use `HGate` wherever the code used `H`" in decision.generation_hint
    assert "Keep the rest of the circuit as it is" in decision.generation_hint
    assert decision.retrieval_hint is None
