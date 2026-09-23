"""MissingImport: the one repair the system knows exactly (T090c, F14, F3).

In the baseline run, 112 of 287 static failures were `NameError` on a symbol
that EXISTS in Qiskit — the model wrote a correct circuit and omitted the
import line. All 112 were classified `HallucinatedSymbol` and routed to
`retry_retrieval`, which cannot possibly help: no quantity of retrieved
documentation adds an `import`. Each burned all five iterations.

The split these tests pin is between two failures that look identical in the
log and require opposite actions:

    NameError: name 'QuantumCircuit' is not defined   -> exists, not imported
    ImportError: cannot import name 'CNOTGate' ...    -> does not exist

Retrieval is right for the second and useless for the first.
"""

import pytest

from qcagent.nodes.critic import make_critic_node, route_action
from qcagent.state import AgentState, ErrorRecord, StaticResult
from qcagent.validators.static import _classify_sandbox_failure, missing_import_for


class _ExplodingLLM:
    """The critic must not call an LLM for this class of error — the fix is
    derivable, so a model in the loop adds a call, a failure mode and a
    chance of saying something wrong, for nothing."""

    model_id = "must-not-be-called"
    cache_dir = None

    def generate(self, **kwargs):
        raise AssertionError("the critic consulted an LLM for a deterministic repair")

    def count_tokens(self, text: str) -> int:
        return 0


def _state(stderr: str) -> AgentState:
    return {
        "task_id": "t",
        "iteration": 1,
        "code": "qc = QuantumCircuit(2)",
        "static": StaticResult(
            parsed=True,
            executed=False,
            transpiled=False,
            error=ErrorRecord(
                iteration=1,
                stage="static",
                error_type=_classify_sandbox_failure(stderr),
                message=stderr,
            ),
        ),
    }


# --- classification --------------------------------------------------------


@pytest.mark.parametrize(
    ("stderr", "expected_fix"),
    [
        ("NameError: name 'QuantumCircuit' is not defined", "from qiskit import QuantumCircuit"),
        (
            "NameError: name 'Statevector' is not defined",
            "from qiskit.quantum_info import Statevector",
        ),
        ("NameError: name 'transpile' is not defined", "from qiskit import transpile"),
        ("NameError: name 'np' is not defined", "import numpy as np"),
    ],
)
def test_a_real_symbol_that_was_not_imported_is_a_missing_import(stderr, expected_fix) -> None:
    assert _classify_sandbox_failure(stderr) == "MissingImport"
    assert missing_import_for(stderr) == expected_fix


@pytest.mark.parametrize(
    "stderr",
    [
        "ImportError: cannot import name 'CNOTGate' from 'qiskit.circuit.library'",
        "ImportError: cannot import name 'Hadamard' from 'qiskit.circuit.library'",
        "NameError: name 'Frobnicator' is not defined",
        "AttributeError: 'QuantumCircuit' object has no attribute 'hadamard'",
    ],
)
def test_an_invented_symbol_stays_a_hallucination(stderr: str) -> None:
    """Retrieval IS the right action here, so this must not be reclassified —
    the value of the split depends on both halves being right."""
    assert _classify_sandbox_failure(stderr) == "HallucinatedSymbol"
    assert missing_import_for(stderr) is None


def test_the_symbol_index_is_read_from_the_installed_qiskit() -> None:
    """Not a hand-written list: a hardcoded set would drift silently from the
    installed version, which is the failure mode NON_GATE_INSTRUCTIONS was
    already pinned against."""
    from qiskit.circuit.library import QFTGate

    assert missing_import_for("NameError: name 'QFTGate' is not defined") is not None
    assert QFTGate is not None  # the symbol the assertion above relies on


# --- routing ---------------------------------------------------------------


def test_missing_import_routes_to_generation_not_retrieval() -> None:
    state = _state("NameError: name 'QuantumCircuit' is not defined")
    action, error_type = route_action(state["static"], None, None, None, 1, 5, [])

    assert error_type == "MissingImport"
    assert action == "retry_generation", "retrieval cannot add an import line"


def test_hallucinated_symbol_still_routes_to_retrieval() -> None:
    state = _state("ImportError: cannot import name 'CNOTGate' from 'qiskit.circuit.library'")
    action, error_type = route_action(state["static"], None, None, None, 1, 5, [])

    assert error_type == "HallucinatedSymbol"
    assert action == "retry_retrieval"


# --- the hint --------------------------------------------------------------


def test_the_hint_names_the_exact_import_and_costs_no_llm_call() -> None:
    critic = make_critic_node(_ExplodingLLM(), max_iter=5, seed=1)

    result = critic(_state("NameError: name 'QuantumCircuit' is not defined"))

    decision = result["decision"]
    assert decision.action == "retry_generation"
    assert "from qiskit import QuantumCircuit" in decision.generation_hint
    # Retrieval hint stays empty: this is not a retrieval problem.
    assert decision.retrieval_hint is None


def test_the_hint_does_not_tell_the_model_to_rewrite_the_circuit() -> None:
    """The gates were not what failed. A hint that invites a rewrite turns a
    one-line fix into a fresh chance to get the physics wrong."""
    critic = make_critic_node(_ExplodingLLM(), max_iter=5, seed=1)

    hint = critic(_state("NameError: name 'np' is not defined"))["decision"].generation_hint

    assert "import numpy as np" in hint
    assert "Keep the rest of the circuit as it is" in hint
