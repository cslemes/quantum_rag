"""STEP 0-1 of the family selection: the skill histogram of the benchmark's statements.

TWO VERSIONS. v1 (superseded 2026-10-27): the 96 in-family statements, with the 24
held-out tasks excluded and never opened (`in_family_statements`). v2: all 120
statements (`all_statements`), after the family-held-out slice was dropped (see
`distill-family-selection-v2.md`). v2 keeps the boundary that matters and drops the one
that does not: STATEMENTS ONLY, never a reference circuit; the held-out names no longer
exclude anything. The v1 docstring follows, kept as the record of what v1 did.

FAIRNESS BOUNDARY, v1 (recorded first). This module reads the `prompt` field of the 96
in-family tasks and nothing else. It never opens a reference circuit (`oracle_path`),
and it never reads any of the 24 held-out tasks (`bench/heldout.yaml`): reference
circuits are benchmark-only, and the project's rule is that what a real user would have
is fair while what only the benchmark has is not. Choosing training families from the
held-out tasks would let the held-out slice influence training. Consequence for the
final claim: the result is bounded to "trained for this benchmark's distribution", not
"general Qiskit improvement" (the in-family statements are the benchmark's own).

A skill is a construct, an API surface, a convention or a constraint that a statement
NAMES or ASKS FOR. The lexicon below was written from the data: it started from the
document frequency of the statements' terms, then from reading all 96 statements. Each
skill is a regular expression over the lower-cased statement; a statement counts once
per skill. The lexicon, not the family list, is where judgement enters, which is why it
is code, in the repository, and re-runnable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
TASKS = ROOT / "bench" / "tasks"
HELDOUT = ROOT / "bench" / "heldout.yaml"

# (skill id, description, kind, regex). kind: construct | convention | constraint | algorithm
LEXICON: list[tuple[str, str, str, str]] = [
    (
        "hadamard",
        "Hadamard gates (superposition layer, H on all or on a subset)",
        "construct",
        r"hadamard",
    ),
    (
        "z_hamiltonian_pauli_sum",
        "a Hamiltonian written as a sum of Pauli-Z terms with coefficients",
        "construct",
        r"\bh = |h = sum|hamiltonian|\bz\d\s*\*\s*z\d|z_i\s*\*\s*z_j|\d\s*\*\s*z\d",
    ),
    (
        "diagonal_phase_evolution",
        "the diagonal phase exp(-i*gamma*H) of a Z-type Hamiltonian",
        "construct",
        r"exp\(-i",
    ),
    (
        "multi_body_z_string",
        "a many-body Z*Z*...*Z interaction term (parity phase)",
        "construct",
        r"z\d\s*\*\s*z\d\s*\*\s*z\d|three-body|four-body|five-body|two-body|z_i\s*\*\s*z_j",
    ),
    ("global_phase_tolerance", "equality 'up to global phase'", "convention", r"global phase"),
    (
        "linear_coupling_map",
        "a linear (nearest-neighbour) coupling map, routing overhead, adjacency",
        "constraint",
        r"coupling map|routing|physically adjacent",
    ),
    (
        "restricted_gate_set",
        "decomposition into a restricted gate set (use ONLY RZ, SX, X, CX ...)",
        "constraint",
        r"use only the gates|do not use|decompose|decomposition",
    ),
    (
        "qubit_order_reversal",
        "a reversed / relabelled qubit-ordering convention",
        "convention",
        r"reversed|relabel|qubit-ordering|ordering convention|least significant|most significant",
    ),
    ("ghz_state", "GHZ-type state (full register or a subset of qubits)", "construct", r"ghz"),
    ("bell_state", "Bell state", "construct", r"bell"),
    (
        "w_state",
        "W state (equal superposition of Hamming-weight-1 states)",
        "construct",
        r"\bw state|w-state",
    ),
    (
        "oracle_construction",
        "building an oracle (CNOT / phase) for a given function",
        "construct",
        r"oracle",
    ),
    (
        "ancilla_register_layout",
        "an ancilla / input / output / counting register layout",
        "convention",
        r"ancilla|input register|output register|counting register|eigenstate register",
    ),
    (
        "ancilla_init_x_then_h",
        "initialise the ancilla to |1> with X, Hadamard on all",
        "construct",
        r"initialize (the )?(ancilla|qubit)",
    ),
    (
        "hadamard_on_subset_only",
        "Hadamard on a subset only (not the ancilla)",
        "construct",
        r"qubits? [0-9, \-]+ only|only \(not|not the ancilla",
    ),
    (
        "reversible_boolean_logic",
        "reversible Boolean logic with Toffoli / multi-controlled X",
        "construct",
        r"toffoli|ccx|\bmcx\b|4-controlled",
    ),
    ("xor_parity", "XOR / parity of bits", "construct", r"\bxor\b|parity"),
    ("qft", "the Quantum Fourier Transform (textbook, or its inverse)", "algorithm", r"fourier"),
    (
        "controlled_phase",
        "controlled-phase / controlled-P rotations",
        "construct",
        r"controlled-p|controlled-phase|controlled phase|\bcp\b",
    ),
    ("swap_layer", "a SWAP layer / reversal of qubits", "construct", r"swap"),
    (
        "compose_then_extra_gate",
        "a standard block followed by an additional gate / block",
        "construct",
        r"followed by",
    ),
    (
        "value_via_formula",
        "a parameter given by a formula, not a literal",
        "convention",
        r"via the formula|formula|secret=22|\(k, n_count\)|3/5|2/5|1/2",
    ),
    ("qubo_to_ising", "QUBO to Ising conversion (x = (1 - z) / 2)", "construct", r"qubo"),
    (
        "vqe_fixed_ansatz",
        "a fixed-parameter variational ansatz and its energy",
        "algorithm",
        r"vqe|ansatz|ground-state energy",
    ),
    (
        "grover",
        "Grover search (phase oracle, diffuser, iteration count)",
        "algorithm",
        r"grover|diffuser",
    ),
    ("phase_estimation", "quantum phase estimation", "algorithm", r"phase estimation"),
    (
        "bernstein_vazirani",
        "Bernstein-Vazirani (hidden linear function)",
        "algorithm",
        r"bernstein",
    ),
    ("deutsch_jozsa", "Deutsch-Jozsa", "algorithm", r"deutsch"),
    ("simon", "Simon's algorithm (hidden period)", "algorithm", r"simon"),
    (
        "hidden_bitstring_secret",
        "a hidden bit string / secret / period",
        "construct",
        r"secret|hidden|period",
    ),
    (
        "exact_ket_target",
        "a target state written as an explicit ket sum",
        "construct",
        r"\(\|[01]+>|\(\|[01]+> *\+|sqrt\(",
    ),
    (
        "single_qubit_rotation",
        "a single-qubit rotation with a stated angle (RY, RZ, P)",
        "construct",
        r"\bry\(|\brz\(|\bp\(|rotation|phase gate",
    ),
    (
        "controlled_rotation_decomposition",
        "decomposition of a controlled rotation (CRY) into RY and CX",
        "construct",
        r"controlled-ry|cry|controlled rotation",
    ),
    (
        "unitary_block_not_state",
        "a general-purpose unitary block, not a fixed starting state",
        "convention",
        r"general-purpose|not a fixed starting state",
    ),
    (
        "no_measurement_return_state",
        "return the state, no measurement (statement format, not a skill)",
        "format",
        r"no measurement|return the resulting",
    ),
    ("qubits_remain_zero", "some qubits stay in |0> (GHZ on a subset)", "construct", r"remain"),
    (
        "pauli_ground_energy",
        "ground-state energy of a Pauli-sum Hamiltonian",
        "construct",
        r"ground-state energy|parity-reduced",
    ),
    # Added for v2, after the 24 statements that v1 never read were read:
    (
        "qaoa_p1",
        "a p=1 QAOA circuit (cost layer + RX mixer, fixed angles)",
        "algorithm",
        r"qaoa|mixer",
    ),
    ("maxcut_graph", "a MaxCut graph given by its edges", "construct", r"maxcut|max-cut|\bedge"),
    (
        "full_adder_majority",
        "a full / half adder with sum and carry",
        "construct",
        r"full-adder|full adder|majority|half-adder|half adder",
    ),
]


def in_family_statements() -> dict[str, str]:
    """The `prompt` of each of the 96 in-family tasks, and nothing else of them.

    A held-out task file is skipped by NAME, before it is opened (the file stem is the
    task id), so the held-out slice is not read even to be discarded."""
    held_out = set(yaml.safe_load(HELDOUT.read_text(encoding="utf-8"))["heldout"]["tasks"])
    out: dict[str, str] = {}
    for path in sorted(TASKS.glob("*/*.json")):
        if path.stem in held_out:
            continue
        task = json.loads(path.read_text(encoding="utf-8"))
        out[task["task_id"]] = task["prompt"]
    return out


def all_statements() -> dict[str, str]:
    """v2: the `prompt` of all 120 tasks, and nothing else of them. No reference circuit
    is opened (a test spies on every file the code opens)."""
    out: dict[str, str] = {}
    for path in sorted(TASKS.glob("*/*.json")):
        task = json.loads(path.read_text(encoding="utf-8"))
        out[task["task_id"]] = task["prompt"]
    return out


#: the lexicon v1 used (the first 36 entries); v2 adds three after reading the 24 statements
LEXICON_V1 = LEXICON[:-3]


def histogram(
    statements: dict[str, str] | None = None,
    lexicon: list[tuple[str, str, str, str]] | None = None,
) -> list[dict]:
    statements = statements or all_statements()
    rows = []
    for skill_id, description, kind, pattern in lexicon or LEXICON:
        rx = re.compile(pattern)
        hits = sorted(t for t, text in statements.items() if rx.search(text.lower()))
        rows.append(
            {
                "skill": skill_id,
                "description": description,
                "kind": kind,
                "count": len(hits),
                "share": round(len(hits) / len(statements), 3),
                "tasks": hits,
            }
        )
    rows.sort(key=lambda r: (-r["count"], r["skill"]))
    return rows
