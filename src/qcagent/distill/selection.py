"""STEPS 2-4 of the family selection, as data and arithmetic.

TWO VERSIONS. Everything above `# ---- v2` is v1 (2026-10-25, superseded 2026-10-27): it
applied filter (c), no mechanism identity with a held-out family, against the
held-out slice `heldout-v1`. v2 (below) drops that slice and that filter (the
decision and its reason are in `distill-family-selection-v2.md`) and keeps (a) oracle,
(b) variations, (d) bounded oracle time, plus the two gates that hold held-out at the
statement and answer level.

The qualitative filters (a) oracle, (c) mechanism identity are recorded in `CANDIDATES`
with their reasons; the quantitative ones, (b) the count of distinct parameter
variations and (d) the oracle's time at the qubit counts used, are COMPUTED here.

Mechanism identity (filter c), the operational reading used, from textbook definitions
of the held-out FAMILIES (their names only; no held-out statement or reference is read):
a candidate has identity with a held-out family when (i) the held-out family is a
parameter specialisation of the candidate or the candidate of it (BV is DJ-balanced with
a linear oracle; QAOA with beta = 0 is H plus the cost layer), or (ii) the candidate's
reference construction contains the held-out family's WHOLE construction at 3 or more
qubits as a block (Draper adder contains the QFT; ripple-carry contains the full adder).
A shared primitive (one H and one CX) or an overlapping skeleton is ADJACENCY, reported
but not disqualifying. This reading is the one decision that moves the list most.
"""

from __future__ import annotations

import json
import time
from math import comb, factorial

import numpy as np
from qiskit.quantum_info import SparsePauliOp

from qcagent.distill.skills import ROOT

TARGET_STATEMENTS = 5000  # the figure the cost estimate used; a stated assumption


# ---- (b) distinct parameter variations, in the declared ranges ----------------------


def permutations_count(n_min: int = 3, n_max: int = 7) -> int:
    """Non-identity qubit permutations; n <= 7 keeps the unitary at 128 x 128."""
    return sum(factorial(n) - 1 for n in range(n_min, n_max + 1))


def connected_graph_count(n: int) -> int:
    from qcagent.distill.families.graph_states import connected_graphs

    return len(connected_graphs(n))


def stabilizer_graph_count(n_min: int = 4, n_max: int = 6) -> int:
    """Connected labelled graphs on 4..6 vertices, GHZ's local-Clifford class INCLUDED."""
    return sum(connected_graph_count(n) for n in range(n_min, n_max + 1))


def pauli_string_count(n: int, max_weight: int = 3) -> int:
    return sum(comb(n, w) * 3**w for w in range(1, max_weight + 1))


def pauli_hamiltonian_count(n_min: int = 3, n_max: int = 8, coeffs: int = 16) -> int:
    """2-5 distinct non-identity Pauli strings of weight <= 3, each with a coefficient
    on a 16-value grid (multiples of 0.25 in [-2, 2], zero excluded)."""
    return sum(
        comb(pauli_string_count(n), k) * coeffs**k
        for n in range(n_min, n_max + 1)
        for k in range(2, 6)
    )


def biased_bits_count(n_min: int = 3, n_max: int = 8, grid: int = 18) -> int:
    return sum(grid**n for n in range(n_min, n_max + 1))


def simon_count(n_min: int = 2, n_max: int = 6) -> int:
    """(period s, control position j in the set bits of s): n * 2^(n-1) per n; 2n qubits."""
    return sum(n * 2 ** (n - 1) for n in range(n_min, n_max + 1))


def grover_count(n_min: int = 3, n_max: int = 8, max_marked: int = 3) -> int:
    return sum(comb(2**n, m) for n in range(n_min, n_max + 1) for m in range(1, max_marked + 1))


def w_dicke_count(n_min: int = 3, n_max: int = 8, weights: int = 4) -> int:
    """Weighted W states (integer weights 1..4 over the weight-1 basis states); the
    uniform Dicke states are the n*(k) subset and are far fewer than 200 by themselves."""
    uniform = sum(n - 1 for n in range(n_min, 13))
    return uniform + sum(weights**n for n in range(n_min, n_max + 1))


CAPACITY = {
    "qubit_permutation": permutations_count,
    "stabilizer_graph_states": stabilizer_graph_count,
    "pauli_hamiltonian_energy": pauli_hamiltonian_count,
    "independent_biased_bits": biased_bits_count,
    "simon": simon_count,
    "grover": grover_count,
    "w_dicke": w_dicke_count,
}


# ---- (d) oracle time at the qubit counts used -----------------------------------------


def _seconds(fn) -> float:
    start = time.perf_counter()
    fn()
    return round(time.perf_counter() - start, 3)


def oracle_times() -> dict[str, dict[str, float]]:
    """Measured on this host (one BLAS thread not forced). The exact-diagonalisation wall
    is measured, not assumed."""
    rng = np.random.default_rng(0)

    def energy(n: int) -> float:
        labels = ["".join(rng.choice(list("IXYZ"), n)) for _ in range(5)]
        labels = [label if set(label) != {"I"} else "Z" + label[1:] for label in labels]
        op = SparsePauliOp(labels, coeffs=rng.uniform(-1, 1, 5))
        return _seconds(lambda: np.linalg.eigvalsh(op.to_matrix()))

    return {
        "pauli_energy_exact_diagonalisation_seconds": {str(n): energy(n) for n in (8, 10, 11, 12)},
    }


def table() -> dict:
    return {
        "target_statements": TARGET_STATEMENTS,
        "capacity": {name: fn() for name, fn in CAPACITY.items()},
        "oracle_times": oracle_times(),
    }


if __name__ == "__main__":
    result = table()
    (ROOT / "bench" / "family_selection_capacity.json").write_text(
        json.dumps(result, indent=1) + "\n"
    )
    print(json.dumps(result, indent=1))


# ---- v2: the family-held-out slice is dropped; filter (c) no longer exists -----------
#
# What remains of "held-out" is at the statement and answer level, enforced by the gates
# already built: lexical near-duplicate against every test statement, and strict circuit
# equivalence against all 120 references. So a variation that coincides with a test task
# is removed, and the capacity below is an upper bound less those few instances.


def qft_count(m_max: int = 8) -> int:
    """n-qubit QFT embedded on an ordered subset of m <= m_max qubits, forward or
    inverse, with or without the final SWAP layer."""
    from math import perm

    return sum(perm(m, n) * 4 for m in range(2, m_max + 1) for n in range(2, m + 1))


def qpe_count(n_min: int = 2, n_max: int = 8) -> int:
    """Counting register of n qubits, eigenphase k / 2^n exactly representable."""
    return sum(2**n - 1 for n in range(n_min, n_max + 1))


def kickback_oracle_count(n_min: int = 2, n_max: int = 10) -> int:
    """Bernstein-Vazirani secrets / Deutsch-Jozsa linear balanced oracles: s != 0."""
    return sum(2**n - 1 for n in range(n_min, n_max + 1))


def diagonal_phase_count(
    n_min: int = 3, n_max: int = 8, max_terms: int = 6, coeffs: int = 16
) -> int:
    """H on all qubits, then exp(-i gamma H) with H a sum of Z-strings (any non-empty
    subset of the qubits), coefficients on a 16-value grid. QUBO inputs are another
    way to state the same H."""
    return sum(
        comb(2**n - 1, k) * coeffs**k
        for n in range(n_min, n_max + 1)
        for k in range(1, max_terms + 1)
    )


def reversible_logic_count(k_min: int = 2, k_max: int = 5, max_outputs: int = 4) -> int:
    """Outputs are the AND or the XOR of a non-empty subset of the k inputs, into fresh ancillas."""
    return sum(
        comb(2 * (2**k - 1), m) for k in range(k_min, k_max + 1) for m in range(1, max_outputs + 1)
    )


def qaoa_p1_count(n_min: int = 3, n_max: int = 6, grid: int = 10) -> int:
    """Connected labelled graphs on 3..6 vertices, (gamma, beta) on a grid x grid."""
    from qcagent.distill.families.graph_states import connected_graphs

    return sum(len(connected_graphs(n)) for n in range(n_min, n_max + 1)) * grid * grid


def parity_reduced_h2_like_count(grid: int = 8) -> int:
    """The six coefficients g0..g5 of a parity-reduced 2-qubit Hamiltonian, on a grid."""
    return grid**6


CAPACITY_V2 = {
    **CAPACITY,
    "diagonal_phase_ising": diagonal_phase_count,
    "qft": qft_count,
    "qpe": qpe_count,
    "kickback_bv_dj": kickback_oracle_count,
    "reversible_logic": reversible_logic_count,
    "qaoa_p1": qaoa_p1_count,
    "two_qubit_ansatz_energy": parity_reduced_h2_like_count,
}

#: Skills each family teaches. `primary` = the statement's own subject (the construct or
#: algorithm the statement is ABOUT); `secondary` = skills the family also exercises
#: (conventions, components shared with other families). Built families cost no new
#: construction. A skill is only ever matched from statements (the histogram), never
#: from references.
FAMILY_SKILLS_V2: dict[str, dict] = {
    "qubit_permutation": {
        "built": True,
        "primary": ["qubit_order_reversal", "swap_layer"],
        "secondary": [],
    },
    "stabilizer_graph_states": {
        "built": True,
        "primary": ["ghz_state", "bell_state", "qubits_remain_zero"],
        "secondary": ["exact_ket_target"],
    },
    "pauli_hamiltonian_energy": {
        "built": True,
        "primary": ["pauli_ground_energy", "vqe_fixed_ansatz"],
        "secondary": [],
    },
    "independent_biased_bits": {
        "built": True,
        "primary": [],
        "secondary": ["single_qubit_rotation"],
    },
    "diagonal_phase_ising": {
        "built": False,
        "primary": [
            "diagonal_phase_evolution",
            "multi_body_z_string",
            "qubo_to_ising",
            "z_hamiltonian_pauli_sum",
        ],
        "secondary": [],
    },
    "qft": {"built": False, "primary": ["qft"], "secondary": ["controlled_phase", "swap_layer"]},
    "kickback_bv_dj": {
        "built": False,
        "primary": ["bernstein_vazirani", "deutsch_jozsa"],
        "secondary": [
            "xor_parity",
            "ancilla_init_x_then_h",
            "hidden_bitstring_secret",
            "oracle_construction",
            "ancilla_register_layout",
        ],
    },
    "qpe": {
        "built": False,
        "primary": ["phase_estimation"],
        "secondary": ["controlled_phase", "ancilla_init_x_then_h"],
    },
    "simon": {
        "built": False,
        "primary": ["simon"],
        "secondary": [
            "hidden_bitstring_secret",
            "hadamard_on_subset_only",
            "ancilla_register_layout",
            "oracle_construction",
        ],
    },
    "grover": {"built": False, "primary": ["grover"], "secondary": ["oracle_construction"]},
    "w_dicke": {
        "built": False,
        "primary": ["w_state"],
        "secondary": ["controlled_rotation_decomposition"],
    },
    "reversible_logic": {
        "built": False,
        "primary": ["reversible_boolean_logic", "full_adder_majority"],
        "secondary": ["xor_parity"],
    },
    "qaoa_p1": {"built": False, "primary": ["qaoa_p1", "maxcut_graph"], "secondary": []},
    "two_qubit_ansatz_energy": {
        "built": False,
        "primary": ["vqe_fixed_ansatz", "pauli_ground_energy"],
        "secondary": [],
    },
}

#: Skills that are properties of the statement or the verifier, not of a family
#: (axes on any family, or not separable): never counted as a statement's "own" skill.
NON_FAMILY_SKILLS = {
    "no_measurement_return_state",
    "hadamard",
    "global_phase_tolerance",
    "restricted_gate_set",
    "linear_coupling_map",
    "compose_then_extra_gate",
    "value_via_formula",
    "unitary_block_not_state",
}


def coverage_v2(histogram_rows: list[dict]) -> dict:
    """The reach of the families over the 120 statements, from statements only.

    A statement NEEDS the principal skills it names (a principal skill = one that is the
    PRIMARY skill of some family). It is FULLY reached when every principal skill it needs
    is taught by a chosen family, and PARTLY reached when at least one is. (A statement
    that appends a QFT to an Ising circuit needs both; a family for the Ising circuit alone
    reaches it only partly.) Families are added greedily by the statements they newly make
    fully reached (ties: newly partly reached), after the four built ones, which cost no
    new construction. Secondary skills (conventions, shared components) are reported per
    family and never decide reach."""
    by_skill = {r["skill"]: set(r["tasks"]) for r in histogram_rows}
    principal = sorted({sk for i in FAMILY_SKILLS_V2.values() for sk in i["primary"]})
    need: dict[str, set[str]] = {}
    for sk in principal:
        for t in by_skill.get(sk, set()):
            need.setdefault(t, set()).add(sk)
    statements = set().union(*by_skill.values())
    teaches = {n: set(i["primary"]) for n, i in FAMILY_SKILLS_V2.items()}

    def reached(chosen: set[str]) -> tuple[int, int]:
        taught = set().union(*(teaches[n] for n in chosen)) if chosen else set()
        full = sum(1 for t in statements if need.get(t, set()) <= taught and need.get(t))
        part = sum(1 for t in statements if need.get(t, set()) & taught)
        return full, part

    chosen = {n for n, i in FAMILY_SKILLS_V2.items() if i["built"]}
    full, part = reached(chosen)
    steps = [
        {
            "added": "the four built families",
            "new_constructions": 0,
            "fully_reached": full,
            "partly_reached": part,
        }
    ]
    remaining = {n for n, i in FAMILY_SKILLS_V2.items() if not i["built"]}
    constructions = 0
    while remaining:
        best = max(remaining, key=lambda n: (*reached(chosen | {n}), n))
        new_full, new_part = reached(chosen | {best})
        if (new_full, new_part) == (full, part):
            break
        chosen.add(best)
        remaining.discard(best)
        constructions += 1
        steps.append(
            {
                "added": best,
                "new_constructions": constructions,
                "marginal_fully_reached": new_full - full,
                "fully_reached": new_full,
                "partly_reached": new_part,
                "capacity": CAPACITY_V2[best]() if best in CAPACITY_V2 else None,
                "teaches_primary": sorted(teaches[best]),
            }
        )
        full, part = new_full, new_part
    return {
        "principal_skills": principal,
        "statements": len(statements),
        "greedy": steps,
        "not_fully_reached_by_the_unchosen": sorted(
            t
            for t in statements
            if not need.get(t, set()) <= set().union(*(teaches[n] for n in chosen))
        ),
        "statements_needing_no_principal_skill": sorted(t for t in statements if not need.get(t)),
        "generous_reach_per_family": {
            n: len(set().union(*(by_skill.get(sk, set()) for sk in i["primary"] + i["secondary"])))
            for n, i in FAMILY_SKILLS_V2.items()
        },
    }
