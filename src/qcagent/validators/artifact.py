"""Descriptions of a GENERATED circuit — properties of the artifact only.

The information rule (maintainer, 2026-09-27; T117, T118): what a real user
would have is fair, what only the benchmark has is not. A circuit's own gate
counts, size and output distribution are facts about the artifact that any
user could compute; nothing here is compared with, or computed from, a
reference. "Your circuit produces 25% uniform across four states" says what
the circuit did — more than a fidelity scalar, which only says it is wrong.
"""

import io

from qiskit import QuantumCircuit, qpy
from qiskit.quantum_info import Statevector

MAX_QUBITS_FOR_DISTRIBUTION = 12
TOP_STATES = 6

# Error types produced by COMPARING the artifact with the reference (or the
# reference's distribution/energy/resources). Their messages, payloads and
# even their names carry benchmark-only information, so under the rule they
# never reach the critic or the generator; a neutral note and the artifact's
# own description replace them. Errors about the user's own code or
# declarations (static errors, NonUnitaryCircuit, MissingMeasurement,
# ParameterBindingError, assertion failures) are not in this set.
REFERENCE_DERIVED_ERRORS = frozenset(
    {"WrongGateDecomposition", "EndiannessSwap", "ConceptualAlgorithmError", "ResourceExcess"}
)

FUNCTIONAL_FAILURE_NOTE = (
    "the circuit ran, but its output does not do what the task asks (functional check failed)"
)
RESOURCE_FAILURE_NOTE = (
    "the circuit exceeds the resource budget for this task (too deep or too many CX)"
)


def describe_circuit(qc: QuantumCircuit) -> str:
    lines = [
        f"qubits: {qc.num_qubits}",
        f"gate counts: {dict(sorted(qc.count_ops().items()))}",
        f"depth: {qc.depth()}",
    ]
    if qc.num_qubits <= MAX_QUBITS_FOR_DISTRIBUTION:
        try:
            probabilities = Statevector(qc.remove_final_measurements(inplace=False))
            top = sorted(
                probabilities.probabilities_dict().items(), key=lambda kv: (-kv[1], kv[0])
            )[:TOP_STATES]
            shown = ", ".join(f"|{basis}>: {p:.3f}" for basis, p in top if p > 1e-9)
            lines.append(f"output distribution, most likely states (qubit 0 rightmost): {shown}")
        except Exception as exc:  # noqa: BLE001 — unbound parameters, mid-circuit measurement
            lines.append(f"output distribution: not computable ({type(exc).__name__})")
    return "\n".join(lines)


def describe_qpy(circuit_qpy: bytes) -> str:
    """From the QPY the sandbox produced: data, never re-executed code."""
    with io.BytesIO(circuit_qpy) as buf:
        (qc,) = qpy.load(buf)
    return describe_circuit(qc)


def failure_note(error_type: str) -> str:
    return RESOURCE_FAILURE_NOTE if error_type == "ResourceExcess" else FUNCTIONAL_FAILURE_NOTE
