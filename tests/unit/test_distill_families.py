"""Each pilot family: 20 variations, its oracle and construction agree, and the
check actually can fail (a wrong construction is rejected, not waved through)."""

from __future__ import annotations

import json

import numpy as np
import pytest
from qiskit import QuantumCircuit

from bench.run_single import _load_oracle
from bench.schema import TaskSpec
from qcagent.distill.families import PILOT_FAMILIES, BuilderDisagreement, Family
from qcagent.distill.families.biased_bits import (
    product_distribution,
    reference_counts,
    ry_construction,
    write_counts_oracle,
)
from qcagent.distill.families.graph_states import (
    GraphStates,
    connected_graphs,
    ghz_class,
    graph_state_circuit,
    lc_orbit,
    star,
)
from qcagent.distill.families.pauli_energy import (
    PauliEnergy,
    ground_energy_a,
    ground_energy_b,
    ground_state_circuit,
)
from qcagent.distill.families.permutations import (
    QubitPermutations,
    cycles,
    permutation_unitary,
    swap_construction,
)
from qcagent.distill.strict import circuit_state, circuit_unitary, unitaries_equal


@pytest.mark.parametrize("family", PILOT_FAMILIES, ids=lambda f: f.name)
def test_twenty_distinct_variations_that_all_verify(family: Family) -> None:
    variations = family.variations()
    assert len(variations) == 20
    assert len({v.key for v in variations}) == 20
    assert len({family.statement(v) for v in variations}) == 20
    assert all(r.agreed for r in family.verify_all())


def test_the_pilot_is_four_families_and_eighty_statements() -> None:
    assert [f.name for f in PILOT_FAMILIES] == [
        "qubit_permutation",
        "graph_state",
        "pauli_hamiltonian_energy",
        "independent_biased_bits",
    ]
    assert sum(len(f.variations()) for f in PILOT_FAMILIES) == 80


def test_the_four_oracle_kinds_are_covered() -> None:
    assert {f.oracle_kind for f in PILOT_FAMILIES} == {
        "unitary",
        "statevector",
        "energy",
        "distribution",
    }


def test_variations_are_deterministic() -> None:
    for family in PILOT_FAMILIES:
        assert [v.key for v in family.variations()] == [v.key for v in type(family)().variations()]


# -- permutations -----------------------------------------------------------


def test_the_permutation_definition_moves_qubit_i_to_pi_of_i() -> None:
    # pi = (0 -> 1, 1 -> 0, 2 -> 2): |001> (qubit 0 set) must become |010>.
    matrix = permutation_unitary([1, 0, 2])
    assert matrix[0b010, 0b001] == 1 and matrix[0b001, 0b010] == 1


def test_a_swap_construction_with_the_cycle_order_reversed_is_caught() -> None:
    pi = [1, 2, 0]  # a 3-cycle: order matters
    wrong = QuantumCircuit(3)
    for cycle in cycles(pi):
        for j in range(len(cycle) - 1):  # ascending: the wrong order
            wrong.swap(cycle[j], cycle[j + 1])
    assert unitaries_equal(permutation_unitary(pi), circuit_unitary(swap_construction(pi))).equal
    assert not unitaries_equal(permutation_unitary(pi), circuit_unitary(wrong)).equal


def test_a_permutation_circuit_in_the_reversed_convention_is_not_accepted() -> None:
    family = QubitPermutations()
    v = next(v for v in family.variations() if v.params["n"] == 3 and v.params["pi"] == [1, 0, 2])
    right = swap_construction([1, 0, 2])
    assert family.accepts(v, right).passed
    reversed_register = QuantumCircuit(3)
    reversed_register.swap(1, 2)  # qubit 1 <-> 2 instead of 0 <-> 1
    assert not family.accepts(v, reversed_register).passed


def test_a_disagreeing_family_is_not_usable(monkeypatch: pytest.MonkeyPatch) -> None:
    import qcagent.distill.families.permutations as module

    monkeypatch.setattr(module, "swap_construction", lambda pi: QuantumCircuit(len(pi)))
    with pytest.raises(BuilderDisagreement):
        QubitPermutations().verify_all()


# -- graph states -----------------------------------------------------------


def test_the_ghz_local_clifford_class_is_enumerated_not_assumed() -> None:
    assert (len(connected_graphs(4)), len(ghz_class(4))) == (38, 5)
    assert (len(connected_graphs(5)), len(ghz_class(5))) == (728, 6)
    # Star and complete graph are in it ...
    complete4 = tuple((i, j) for i in range(4) for j in range(i + 1, 4))
    assert star(4) in ghz_class(4) and complete4 in ghz_class(4)
    # ... and local complementation preserves it.
    assert lc_orbit(star(5), 5) == ghz_class(5)


def test_no_selected_graph_is_in_ghzs_class_or_disconnected() -> None:
    for v in GraphStates().variations():
        n, edges = v.params["n"], tuple(tuple(e) for e in v.params["edges"])
        assert edges not in ghz_class(n)
        assert edges in set(connected_graphs(n))


def test_graph_state_closed_form_and_circuit_agree_on_a_hand_case() -> None:
    # Single edge 0-1: amplitudes (1, 1, 1, -1)/2 over k = 0..3.
    family = GraphStates()
    v = next(iter(family.variations()))
    built = graph_state_circuit(v.params["n"], tuple(map(tuple, v.params["edges"])))
    assert family.accepts(v, built).passed
    from qcagent.distill.families.graph_states import graph_state_vector

    assert np.allclose(graph_state_vector(2, ((0, 1),)), np.array([1, 1, 1, -1]) / 2)


# -- Pauli Hamiltonians ------------------------------------------------------


def test_the_two_energy_builders_agree_and_the_reference_circuit_passes_check_energy() -> None:
    family = PauliEnergy()
    for v in family.variations():
        labels, coeffs = v.params["labels"], v.params["coeffs"]
        assert abs(ground_energy_a(labels, coeffs) - ground_energy_b(labels, coeffs)) < 1e-9
        assert family.accepts(v, ground_state_circuit(labels, coeffs)).passed


def test_calibration_cases_hold_for_both_builders() -> None:
    checks = PauliEnergy().calibrate()
    assert len(checks) >= 24 and all(c.passed for c in checks)


def test_a_wrong_state_fails_the_energy_acceptance() -> None:
    family = PauliEnergy()
    v = family.variations()[0]
    labels, coeffs = v.params["labels"], v.params["coeffs"]
    # The highest eigenvector is not a ground state unless the spectrum is flat.
    from qiskit.circuit.library import StatePreparation
    from qiskit.quantum_info import SparsePauliOp

    _, vectors = np.linalg.eigh(SparsePauliOp(labels, coeffs=coeffs).to_matrix())
    top = QuantumCircuit(v.params["n"])
    top.append(StatePreparation(vectors[:, -1]), range(v.params["n"]))
    assert not family.accepts(v, top).passed


# -- biased bits and the distribution path ----------------------------------


def test_hand_computed_product_distribution() -> None:
    # p = (0.25, 0.75): qubit 0 is 1 w.p. 0.25, qubit 1 is 1 w.p. 0.75.
    hand = np.array([0.1875, 0.0625, 0.5625, 0.1875])  # k = 0, 1, 2, 3
    assert np.allclose(product_distribution([0.25, 0.75]), hand)
    built = np.abs(circuit_state(ry_construction([0.25, 0.75]))) ** 2
    assert np.allclose(built, hand)


def test_the_distribution_loader_round_trips_through_the_suite_loader(tmp_path) -> None:
    path = tmp_path / "oracle.json"
    write_counts_oracle(path, [0.25, 0.75])
    task = TaskSpec(
        task_id="t",
        tier="t1",
        prompt="x",
        n_qubits=2,
        oracle_kind="distribution",
        oracle_path=str(path),
        tolerance=0.99,
    )
    counts = _load_oracle(task)
    assert counts == reference_counts([0.25, 0.75])
    assert counts == {"00": 187500, "01": 62500, "10": 562500, "11": 187500}
    assert json.loads(path.read_text())["p"] == [0.25, 0.75]
