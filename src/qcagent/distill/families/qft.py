"""Family Q: the Quantum Fourier Transform on an ordered subset of qubits (unitary).

Closed form (the oracle). For the target qubits t_0..t_{n-1} (t_0 is the least significant bit
of the n-bit number x), N = 2^n:
    forward:  |x> -> N^{-1/2} sum_y exp(+2 pi i x y / N) |y>
    inverse:  |x> -> N^{-1/2} sum_y exp(-2 pi i x y / N) |y>     (the sign of the exponent flipped)
and, when the statement says the final SWAP layer is OMITTED, the output register is the
bit-reversal of y: |x> -> N^{-1/2} sum_y exp(+-2 pi i x y / N) |bitrev(y)>. Qubits that are not
targets are left alone. The oracle is that matrix written entry by entry, embedded in the
m-qubit register by bit manipulation.

THE STATEMENT'S FORMULA IS THE CONTRACT, in all four cells. With the SWAP layer the inverse is
also the conjugate transpose of the forward transform. WITHOUT it, it is NOT: the inverse here
is "inverse DFT, output bit-reversed" (R F^dagger), while the adjoint of the forward no-swap
circuit, which is what Qiskit's `QFT(do_swaps=False).inverse()` builds, is "input bit-reversed"
(F^dagger R), a different matrix. Until 2026-11-12 the oracle was the adjoint while the statement
gave the formula above: in train-v1 that cell rejected 106 answers that satisfied their statement
and accepted 4 that did not (report-notes.md). `test_distill_family_qft.py` now checks the
statement's own formula, written a third time, against the oracle in every cell.

Construction (shares no code with the oracle): H on t_j and controlled-phase gates, top
qubit first, optional swap layer; the inverse negates every controlled-phase angle (the complex
conjugate of the circuit), it does not reverse the circuit.
"""

from __future__ import annotations

import itertools
import math
import random

import numpy as np
from qiskit import QuantumCircuit

from qcagent.distill.families.base import Check, Family, Variation, Verification
from qcagent.distill.strict import circuit_unitary, unitaries_equal


def _bitrev(y: int, n: int) -> int:
    return int(format(y, f"0{n}b")[::-1], 2)


def qft_unitary(m: int, targets: list[int], inverse: bool, swaps: bool) -> np.ndarray:
    """The oracle: the DFT (or its inverse, optionally bit-reversed) on `targets`, identity elsewhere."""
    n = len(targets)
    size = 1 << n
    omega = np.exp(2j * math.pi / size)
    dft = np.array([[omega ** (x * y) for x in range(size)] for y in range(size)]) / math.sqrt(size)
    if inverse:
        # the sign of the exponent flipped. BEFORE the bit reversal below, never after it as a
        # conjugate transpose: that order gave the adjoint of the no-swap transform, which is not
        # the matrix the statement spells out (module docstring).
        dft = dft.conj()
    if not swaps:
        # output register y is read bit-reversed: row y of the DFT lands on row bitrev(y)
        permuted = np.zeros_like(dft)
        for y in range(size):
            permuted[_bitrev(y, n)] = dft[y]
        dft = permuted
    target_mask = sum(1 << q for q in targets)
    matrix = np.zeros((1 << m, 1 << m), dtype=complex)
    for b in range(1 << m):
        x = sum(((b >> q) & 1) << j for j, q in enumerate(targets))
        rest = b & ~target_mask
        for y in range(size):
            out = rest | sum(((y >> j) & 1) << q for j, q in enumerate(targets))
            matrix[out, b] = dft[y, x]
    return matrix


def qft_construction(m: int, targets: list[int], inverse: bool, swaps: bool) -> QuantumCircuit:
    """The ladder, top qubit first. The inverse is the SAME gate order with every angle negated
    (H and SWAP are real, so that is the complex conjugate of the circuit): with the swap layer it
    equals the reversed circuit, without it it does not, and the statement asks for this one."""
    n = len(targets)
    sign = -1.0 if inverse else 1.0
    circuit = QuantumCircuit(m)
    for j in range(n - 1, -1, -1):
        circuit.h(targets[j])
        for k in range(j - 1, -1, -1):
            circuit.cp(sign * math.pi / 2 ** (j - k), targets[k], targets[j])
    if swaps:
        for i in range(n // 2):
            circuit.swap(targets[i], targets[n - 1 - i])
    return circuit


class QFT(Family):
    name = "qft"
    oracle_kind = "unitary"
    closed_form = True

    M_RANGE = range(2, 7)  # register sizes; capacity at m <= 8 is in selection.qft_count

    def variations(self, count: int = 20) -> list[Variation]:
        rng = random.Random("qft-v1")
        pool: list[tuple] = []
        for m in self.M_RANGE:
            for n in range(2, m + 1):
                for targets in itertools.permutations(range(m), n):
                    for inverse in (False, True):
                        for swaps in (True, False):
                            pool.append((m, list(targets), inverse, swaps))
        rng.shuffle(pool)
        # stratify by register size so the sample is not all the (far more numerous) m = 6 cases
        by_m: dict[int, list[tuple]] = {}
        for item in pool:
            by_m.setdefault(item[0], []).append(item)
        chosen: list[tuple] = []
        sizes = sorted(by_m)
        while len(chosen) < count:
            for m in sizes:
                if by_m[m] and len(chosen) < count:
                    chosen.append(by_m[m].pop())
        return [
            Variation(
                self.name,
                i,
                {"m": m, "targets": targets, "inverse": inverse, "swaps": swaps},
            )
            for i, (m, targets, inverse, swaps) in enumerate(chosen)
        ]

    def statement(self, v: Variation) -> str:
        p = v.params
        m, targets, inverse, swaps = p["m"], p["targets"], p["inverse"], p["swaps"]
        n = len(targets)
        order = ", ".join(f"qubit {q}" for q in targets)
        which = "inverse Quantum Fourier Transform" if inverse else "Quantum Fourier Transform"
        sign = "-" if inverse else "+"
        text = (
            f"Build a {m}-qubit Qiskit circuit that applies the {which} to the {n} qubits "
            f"({order}), in that order, where the first listed qubit is the least significant bit "
            f"of the {n}-bit number x. On a basis state |x> the transform must give "
            f"2^(-{n}/2) * sum over y of exp({sign}2*pi*i*x*y/2^{n}) |y>, with y read in the same "
            f"bit order."
        )
        if not swaps:
            text += (
                " Do NOT include the final SWAP layer: the output register is left in "
                "bit-reversed order, so the circuit gives |x> -> 2^(-{n}/2) * sum over y of "
                "exp({sign}2*pi*i*x*y/2^{n}) |bitrev(y)>, bitrev reversing the {n} bits of y."
            ).format(n=n, sign=sign)
        others = [q for q in range(m) if q not in targets]
        if others:
            text += " The other qubits (" + ", ".join(str(q) for q in others) + ") are not touched."
        text += (
            " Use Qiskit's qubit numbering (qubit 0 is the least significant bit of the "
            "register). The circuit's unitary must match exactly, up to global phase. No "
            "measurement, and do not use qiskit.circuit.library.QFT."
        )
        return text

    def verify(self, v: Variation) -> Verification:
        p = v.params
        oracle = qft_unitary(p["m"], p["targets"], p["inverse"], p["swaps"])
        built = circuit_unitary(qft_construction(p["m"], p["targets"], p["inverse"], p["swaps"]))
        result = unitaries_equal(oracle, built)
        return Verification(
            v, [Check("ladder_construction_vs_dft_matrix", result.equal, result.max_abs_diff)]
        )

    def accepts(self, v: Variation, circuit: QuantumCircuit) -> Check:
        p = v.params
        if circuit.num_qubits != p["m"]:
            return Check("strict_unitary", False, float("inf"), "wrong qubit count")
        result = unitaries_equal(
            qft_unitary(p["m"], p["targets"], p["inverse"], p["swaps"]), circuit_unitary(circuit)
        )
        return Check("strict_unitary", result.equal, result.max_abs_diff)

    def calibrate(self) -> list[Check]:
        """Limit case: the 1-qubit-sized transform is the Hadamard, and the 2-qubit one is known."""
        h = qft_unitary(1, [0], False, True)
        hadamard = np.array([[1, 1], [1, -1]]) / math.sqrt(2)
        out = [Check("n1_is_hadamard", unitaries_equal(h, hadamard).equal)]
        f4 = qft_unitary(2, [0, 1], False, True)
        expect = np.array([[1j**(x * y) for x in range(4)] for y in range(4)]) / 2
        out.append(Check("n2_is_4x4_dft", unitaries_equal(f4, expect).equal))
        return out
