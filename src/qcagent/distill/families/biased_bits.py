"""Family 5: independent biased bits (distribution).

Closed form (the oracle): the product distribution, kron of [1-p_i, p_i] with
qubit 0 the LAST factor, so P(k) = prod_i (p_i if bit i of k else 1-p_i).
Construction: RY(2 asin sqrt(p_i)) on qubit i, exact probabilities from the
statevector.

The task asks for a circuit with a final measurement, judged by the cascade's
`check_distribution` (sampled counts, Hellinger fidelity) unchanged. That check
has never run on a real task: `tests/unit/test_distill_distribution_path.py`
validates it on a hand-computed case before this family is used to accept
anything.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit

from qcagent.distill.families.base import Check, Family, Variation, Verification
from qcagent.distill.strict import circuit_state, distributions_equal
from qcagent.validators.semantic import check_distribution

#: reference counts are the exact distribution scaled to this many shots
REFERENCE_SHOTS = 1_000_000
HELLINGER_TOLERANCE = 0.99  # the suite's own tolerance for distribution tasks
#: the exact comparison added on top of the sampled one (see `accepts`)
EXACT_TOLERANCE = 1e-3
#: a variation is used only if reversing the register changes its distribution
#: by at least this much, so the bit-order trap is something the data can show
MIN_REVERSAL_EFFECT = 0.05
P_GRID = [round(0.05 * k, 2) for k in range(1, 20) if k != 10]


def product_distribution(p: list[float]) -> np.ndarray:
    """The oracle: analytic kron, qubit 0 the last factor."""
    out = np.array([1.0])
    for p_i in reversed(p):  # highest qubit first = outermost factor
        out = np.kron(out, np.array([1.0 - p_i, p_i]))
    return out


def reference_counts(p: list[float]) -> dict[str, int]:
    """Bitstring keys in Qiskit's counts convention (leftmost = highest qubit)."""
    n = len(p)
    probs = product_distribution(p)
    return {
        format(k, f"0{n}b"): round(probs[k] * REFERENCE_SHOTS)
        for k in range(1 << n)
        if probs[k] > 0
    }


def write_counts_oracle(path: Path, p: list[float]) -> None:
    """The oracle file format `bench/run_single._load_oracle` reads for the
    distribution kind."""
    path.write_text(json.dumps({"counts": reference_counts(p), "p": p}, indent=2) + "\n")


def ry_construction(p: list[float]) -> QuantumCircuit:
    circuit = QuantumCircuit(len(p))
    for i, p_i in enumerate(p):
        circuit.ry(2 * np.arcsin(np.sqrt(p_i)), i)
    return circuit


class BiasedBits(Family):
    name = "independent_biased_bits"
    oracle_kind = "distribution"
    closed_form = True

    def variations(self) -> list[Variation]:
        rng = random.Random("independent_biased_bits-v1")
        out = []
        seen: set[tuple[float, ...]] = set()
        for n in [3] * 10 + [4] * 10:
            while True:
                p = [rng.choice(P_GRID) for _ in range(n)]
                effect = np.max(np.abs(product_distribution(p) - product_distribution(p[::-1])))
                if effect >= MIN_REVERSAL_EFFECT and tuple(p) not in seen:
                    break
            seen.add(tuple(p))
            out.append(Variation(self.name, len(out), {"n": n, "p": p}))
        return out

    def statement(self, v: Variation) -> str:
        n, p = v.params["n"], v.params["p"]
        biases = ", ".join(f"qubit {i}: {p_i}" for i, p_i in enumerate(p))
        return (
            f"Build a {n}-qubit circuit that, when all qubits are measured in the computational "
            f"basis, gives independent bits: each qubit i is 1 with probability p_i and 0 "
            f"otherwise, with p_i as follows ({biases}). Use Qiskit's qubit numbering (qubit 0 "
            f"is the rightmost bit of a measured bitstring). The circuit must end with a "
            f"measurement of all qubits."
        )

    def verify(self, v: Variation) -> Verification:
        p = v.params["p"]
        result = distributions_equal(
            product_distribution(p), np.abs(circuit_state(ry_construction(p))) ** 2, atol=1e-12
        )
        return Verification(
            v, [Check("ry_construction_vs_analytic_kron", result.equal, result.max_abs_diff)]
        )

    def accepts(self, v: Variation, circuit: QuantumCircuit) -> Check:
        p = v.params["p"]
        if circuit.num_qubits != v.params["n"]:
            return Check("check_distribution", False, 1.0, "wrong qubit count")
        if "measure" not in circuit.count_ops():
            return Check("check_distribution", False, 1.0, "no measurement")
        verdict = check_distribution(circuit, reference_counts(p))
        # The sampled Hellinger check (0.99, three seeds) cannot tell a register
        # that is bit-reversed from the right one when the biases are close: a
        # reversed (0.75, 0.8, 0.7) reads above 0.99. So the exact output
        # distribution is also compared, strictly, and both must pass.
        exact = distributions_equal(
            product_distribution(p), np.abs(circuit_state(circuit)) ** 2, atol=EXACT_TOLERANCE
        )
        return Check(
            "check_distribution_and_exact",
            verdict.hellinger_fidelity >= HELLINGER_TOLERANCE and exact.equal,
            exact.max_abs_diff,
            f"hellinger={verdict.hellinger_fidelity:.4f}",
        )
