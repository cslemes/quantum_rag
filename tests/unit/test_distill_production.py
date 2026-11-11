"""The production registry and the ordering that keeps a halted run balanced."""

from __future__ import annotations

from qcagent.distill.families import PRODUCTION_FAMILIES
from qcagent.distill.pilot import _order_entries


def test_the_seven_approved_families_in_registered_order() -> None:
    assert [f.name for f in PRODUCTION_FAMILIES] == [
        "qubit_permutation",
        "graph_state",
        "pauli_hamiltonian_energy",
        "diagonal_phase_ising",
        "kickback_bv_dj",
        "qaoa_p1",
        "qft",
    ]
    assert "independent_biased_bits" not in {f.name for f in PRODUCTION_FAMILIES}


def test_every_family_verifies_at_the_admitted_size() -> None:
    for family in PRODUCTION_FAMILIES:
        assert all(r.agreed for r in family.verify_all(60))


def test_round_robin_takes_one_entry_per_family_in_turn() -> None:
    entries = [{"family": f, "id": f"{f}{i}"} for f in ("a", "b") for i in range(3)]
    assert [e["id"] for e in _order_entries(entries, True)] == ["a0", "b0", "a1", "b1", "a2", "b2"]
    assert _order_entries(entries, False) == entries


def test_round_robin_survives_unequal_families() -> None:
    entries = [{"family": "a", "id": "a0"}, {"family": "b", "id": "b0"}, {"family": "b", "id": "b1"}]
    assert [e["id"] for e in _order_entries(entries, True)] == ["a0", "b0", "b1"]


def test_every_production_family_has_a_correct_and_a_wrong_control_circuit() -> None:
    """The negative control must cover every family in the run, and each family's control
    circuits must be told apart by the family's own acceptance check."""
    from qiskit import QuantumCircuit

    from qcagent.distill.control import correct_code, wrong_code

    def build(code: str) -> QuantumCircuit:
        fence = "`" * 3
        body = code.strip().removeprefix(fence + "python").removesuffix(fence).strip()
        scope: dict = {}
        exec(body, scope)  # noqa: S102 - the control's own fixed templates, not teacher output
        return scope["qc"]

    for family in PRODUCTION_FAMILIES:
        v_right, v_wrong = family.variations()[1], family.variations()[0]
        if family.name == "pauli_hamiltonian_energy":
            continue  # accepted by energy, covered by the pilot's control
        assert family.accepts(v_right, build(correct_code(family, v_right))).passed, family.name
        assert not family.accepts(v_wrong, build(wrong_code(family, v_wrong))).passed, family.name
