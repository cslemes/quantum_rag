"""Regression tests for bench/validate_oracles.py's independent-construction
checks (T050, FR-018) — locking in two real findings from building the T1
oracles (research.md D3c/D3d):

1. Checks 1-2 (exact `Operator.equiv`) catch a QFT decomposition bug
   unconditionally — no sampling tolerance involved.
2. The ORIGINAL sanity-3-seeds design (comparing a measured QFT run against
   a target derived from the SAME primary circuit) was blind to any
   phase-only bug in a unitary-oracle family, because QFT maps any
   computational-basis input to a uniform-magnitude output regardless of
   whether the phases are correct. The fix (round-trip through the
   independent alternative's inverse) is what actually catches it — this
   test protects that fix from regressing back to the blind version.
"""

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import QFTGate, StatePreparation
from qiskit.quantum_info import Operator, Statevector, hellinger_fidelity

from qcagent.validators.simulator import make_simulator

# Same values as bench/validate_oracles.py's _SANITY_SEEDS/_SANITY_SHOTS —
# duplicated rather than imported: `bench` isn't on pytest's import path
# (only `src/qcagent` is installed as a package), and this test exists to
# verify the underlying phenomenon, not to depend on that module's internals.
_SANITY_SEEDS = (1, 2, 3)
_SANITY_SHOTS = 8192


def _qft_correct(n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    for j in reversed(range(n)):
        qc.h(j)
        for k in range(j):
            qc.cp(np.pi / (2 ** (j - k)), k, j)
    for i in range(n // 2):
        qc.swap(i, n - 1 - i)
    return qc


def _qft_wrong_sign(n: int) -> QuantumCircuit:
    """Computes the INVERSE QFT throughout — an easy, realistic mistake."""
    qc = QuantumCircuit(n)
    for j in reversed(range(n)):
        qc.h(j)
        for k in range(j):
            qc.cp(-np.pi / (2 ** (j - k)), k, j)
    for i in range(n // 2):
        qc.swap(i, n - 1 - i)
    return qc


def test_operator_equiv_rejects_a_wrong_sign_qft_unconditionally() -> None:
    """Checks 1-2's actual guarantee: exact, not probabilistic."""
    n = 8
    library = QuantumCircuit(n)
    library.append(QFTGate(n), range(n))

    assert Operator(_qft_correct(n)).equiv(Operator(library))
    assert not Operator(_qft_wrong_sign(n)).equiv(Operator(library))


def test_measuring_against_a_primary_derived_target_is_blind_to_a_phase_bug() -> None:
    """Sanity check that the ORIGINAL design's blind spot is real, not a
    hypothetical: QFT of any basis state is uniform-magnitude regardless of
    whether the phases are right, so comparing measured counts against a
    target computed FROM THE BUGGY CIRCUIT ITSELF is fidelity=1.0 even
    though the circuit is functionally wrong. This is a fast, exact
    (no-simulator) analytic check of the failure mode the round-trip fix
    exists to close.
    """
    n = 8
    prep = QuantumCircuit(n)
    prep.x(0)

    correct_dist = Statevector(prep.compose(_qft_correct(n))).probabilities_dict(decimals=10)
    buggy_dist = Statevector(prep.compose(_qft_wrong_sign(n))).probabilities_dict(decimals=10)

    assert hellinger_fidelity(buggy_dist, correct_dist) == 1.0


def test_round_trip_sanity_check_catches_a_wrong_sign_qft() -> None:
    """The actual fix: composing the (buggy) primary with the INDEPENDENT
    alternative's inverse turns a phase bug into measurable leakage away
    from a sharp target. Runs through a real AerSimulator, same as
    check_sanity_seeds itself, so this also protects against the fix being
    silently reverted to the blind version.
    """
    n = 8
    prep = QuantumCircuit(n)
    prep.x(0)
    library = QuantumCircuit(n)
    library.append(QFTGate(n), range(n))
    library_inverse = library.inverse()

    full = prep.compose(_qft_wrong_sign(n)).compose(library_inverse)
    measured = full.copy()
    measured.measure_all()
    expected = Statevector(prep).probabilities_dict(decimals=10)

    fidelities = []
    for seed in _SANITY_SEEDS:
        sim = make_simulator(n, seed=seed)
        transpiled = transpile(measured, sim, seed_transpiler=seed)
        result = sim.run(transpiled, shots=_SANITY_SHOTS).result()
        fidelities.append(hellinger_fidelity(result.get_counts(), expected))

    mean_fid = float(np.mean(fidelities))
    assert mean_fid < 0.5  # nowhere near SANITY_FIDELITY_MIN=0.98 — clearly caught


def test_inverted_stateprepation_round_trip_survives_aer_without_predecompose() -> None:
    """Regression coverage for a real engineering bug found while
    generalizing the round-trip design to statevector-oracle families (D3e,
    research.md): `StatePreparation(...).inverse()` decomposes into
    "multiplexer" instructions that CRASH Aer with a SEGFAULT — not a
    catchable Python exception — when handed to `transpile()` without being
    pre-decomposed to standard gates first. `check_sanity_seeds` in
    bench/validate_oracles.py works around this with `.decompose(reps=8)`
    before `transpile()`; this test exercises the exact same shape (a
    StatePreparation-based circuit composed with an INVERTED
    StatePreparation, measured, transpiled, run) to catch a future Qiskit/
    Aer version regressing this workaround's necessity or effectiveness.
    `bench` is not on pytest's import path (see module docstring), so this
    duplicates the decompose step rather than covering
    bench/validate_oracles.py's own code directly — it protects the
    UNDERLYING behavior the fix depends on, not the fix's call site.
    """
    target = np.array([1, 0, 0, 1], dtype=complex) / np.sqrt(2)
    alt_prep = QuantumCircuit(2)
    alt_prep.append(StatePreparation(target), range(2))

    primary = QuantumCircuit(2)
    primary.h(0)
    primary.cx(0, 1)

    full = primary.compose(alt_prep.inverse())
    measured = full.copy()
    measured.measure_all()
    measured = measured.decompose(reps=8)  # the fix under test

    sim = make_simulator(2, seed=1)
    transpiled = transpile(measured, sim, seed_transpiler=1)
    result = sim.run(transpiled, shots=1024).result()  # must not crash the process
    counts = result.get_counts()
    assert counts.get("00", 0) == 1024  # correct primary round-trips exactly to |00>
