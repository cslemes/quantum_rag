"""What reaches the critic (T117, F31).

The rule (maintainer, 2026-09-27): what a real user would have is fair; what
only the benchmark has is not. The case that motivated it, from the RunPod
arm: the generator wrote GROVER for a Deutsch-Jozsa task, the critic saw only
the code and "fidelidade=0.0000", and asked for a better Grover — five times.
"""

import io

from qiskit import QuantumCircuit, qpy
from qiskit.circuit.library import GroverOperator

from qcagent.nodes.critic import _build_hint_prompt, describe_generated_circuit
from qcagent.state import ErrorRecord, SemanticResult, StaticResult

DJ_SPEC = (
    "Implement the Deutsch-Jozsa circuit for the constant oracle f(x) = 0 on a 3-bit input, "
    "ancilla on qubit 3."
)


def _qpy(qc: QuantumCircuit) -> bytes:
    buf = io.BytesIO()
    qpy.dump(qc, buf)
    return buf.getvalue()


def _grover_for_dj_state() -> dict:
    oracle = QuantumCircuit(2)
    oracle.cz(0, 1)
    qc = QuantumCircuit(2)
    qc.h([0, 1])
    qc.compose(GroverOperator(oracle), inplace=True)
    return {
        "spec": DJ_SPEC,
        "code": "from qiskit.circuit.library import GroverOperator\n...",
        "static": StaticResult(
            parsed=True, executed=True, transpiled=True, error=None, circuit_qpy=_qpy(qc)
        ),
        "semantic": SemanticResult(
            state_equiv=False,
            passed=False,
            error=ErrorRecord(
                iteration=1,
                stage="semantic",
                error_type="WrongGateDecomposition",
                message="estado gerado diverge da referência (fidelidade=0.0000)",
                payload={
                    "expected_gate_counts": {"h": 7, "x": 1},
                    "actual_gate_counts": {"Q": 1},
                    "direct_fidelity": 0.0,
                },
            ),
        ),
    }


def test_the_critic_sees_the_task_and_the_artifact() -> None:
    prompt = _build_hint_prompt(
        "retry_generation", "WrongGateDecomposition", _grover_for_dj_state()
    )

    assert DJ_SPEC in prompt  # the user always has the task
    assert "gate counts:" in prompt  # properties of the GENERATED circuit
    assert "output distribution" in prompt
    assert "functional check failed" in prompt


def test_nothing_only_the_benchmark_has_reaches_the_critic() -> None:
    prompt = _build_hint_prompt(
        "retry_generation", "WrongGateDecomposition", _grover_for_dj_state()
    )

    assert "fidelidade" not in prompt and "fidelity" not in prompt.lower()
    assert "expected" not in prompt.lower()
    assert "'h': 7" not in prompt  # the reference's gate counts
    assert "WrongGateDecomposition" not in prompt  # classification computed from the oracle


def test_the_artifact_description_is_the_circuits_own() -> None:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    state = {
        "static": StaticResult(
            parsed=True, executed=True, transpiled=True, error=None, circuit_qpy=_qpy(qc)
        )
    }
    description = describe_generated_circuit(state)
    assert "qubits: 2" in description
    assert "'cx': 1" in description and "'h': 1" in description
    assert "|00>: 0.500" in description and "|11>: 0.500" in description


def test_a_parameterized_circuit_is_described_without_its_distribution() -> None:
    from qiskit.circuit import Parameter

    qc = QuantumCircuit(1)
    qc.rx(Parameter("theta"), 0)
    state = {
        "static": StaticResult(
            parsed=True, executed=True, transpiled=True, error=None, circuit_qpy=_qpy(qc)
        )
    }
    assert "output distribution: not computable" in describe_generated_circuit(state)


def test_static_failures_keep_their_exact_message_and_gain_the_task() -> None:
    """A static error message comes from executing the user's own code, not
    from the reference, so it stays — the rule only removes oracle-derived
    information."""
    state = {
        "spec": DJ_SPEC,
        "code": "from qiskit.circuit.library import H",
        "static": StaticResult(
            parsed=True,
            executed=False,
            transpiled=False,
            error=ErrorRecord(
                iteration=1,
                stage="static",
                error_type="HallucinatedSymbol",
                message="ImportError: cannot import name 'H'",
            ),
        ),
    }
    prompt = _build_hint_prompt("retry_retrieval", "HallucinatedSymbol", state)
    assert DJ_SPEC in prompt
    assert "ImportError: cannot import name 'H'" in prompt
    assert "gate counts" not in prompt  # there is no circuit to describe
