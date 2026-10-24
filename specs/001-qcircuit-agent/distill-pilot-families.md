# Distillation pilot: family specifications

Status: specification, 2026-10-24. Nothing here has generated data or spent
money. Families 1, 2, 3 and 5 approved; family 4 changed (below).

## The rule for how a family is verified

- **A closed form exists: it is the oracle.** The oracle is the specification
  written down directly; the circuit builders are independent constructions
  checked against it. This is stronger than two constructions agreeing,
  because agreement can be a shared error and the closed form shares no code
  with either construction.
- **No closed form: two independent constructions check each other**, and
  analytic limit cases act as calibration points that both must reproduce
  exactly before the family is used.
- Every comparison is STRICT: equal up to global phase, no qubit-reversal or
  permutation search, no tolerance for endianness. A disagreement blocks the
  builder until resolved and recorded.

## Conventions (apply to every family)

- Qiskit little-endian. Qubit 0 is the least significant bit. Basis index
  `k = sum_i b_i 2^i`. A statevector or distribution is indexed by `k`.
- Pauli labels follow Qiskit: the LEFTMOST character acts on the HIGHEST qubit,
  the rightmost on qubit 0. Any hand-built kron product states its order.

## 1. Qubit permutations (unitary)

- **Oracle (definition):** for a permutation pi of the n qubits, the unitary
  `P|b_{n-1}..b_0> = |c_{n-1}..c_0>` with `c_{pi(i)} = b_i`, as a permutation
  matrix over basis indices built by bit manipulation.
- **Construction:** SWAP circuit from the cycle decomposition of pi.
- n = 3, 4; 20 permutations, identity excluded.

## 2. Modular constant adder, modulus 2^n (unitary)

- **Oracle (definition):** `x -> (x + c) mod 2^n` on the n-qubit register
  (qubit 0 least significant), the arithmetic permutation matrix. The modulus
  is 2^n, fixed for the pilot; arbitrary N would need machinery the two
  constructions would share.
- **Construction A, ripple-carry:** Cuccaro MAJ/UMA with the constant loaded
  into an ancilla register by X gates, final carry dropped. Uses ancillas: the
  compared object is the n-qubit block with ancillas at |0>, and the builder
  also verifies that the ancillas return to |0> for every input.
- **Construction B, Draper:** QFT, phase rotations for c, inverse QFT. No
  ancillas. Mechanism independent of A; their failure modes are documented and
  disjoint (ancilla chaining and QFT loop direction were two of the five method
  errors independent construction caught in the 120 references).
- Both are checked against the oracle and against each other.
- n = 3, 4; 20 constants in 1 .. 2^n - 1.

## 3. Graph states (statevector)

- **Oracle (closed form):** `|G> = 2^{-n/2} sum_x (-1)^{sum_{(i,j) in E} x_i x_j} |x>`.
- **Construction:** H on every qubit, CZ per edge.
- **Selection:** connected graphs on 4 and 5 vertices. For each candidate the
  local-Clifford equivalence class is ENUMERATED (breadth-first search under
  local complementation) and any graph in the class of the GHZ state (the star)
  is excluded, so no representative of GHZ's class passes under another name.
  Disconnected graphs are not used: a component that is a pair or a 3-vertex
  path is itself GHZ-class. Enumerated (labelled, connected): n=4, 38 graphs, of
  which 5 are in GHZ's class and 33 are not; n=5, 728 graphs, 6 in GHZ's class,
  722 not. 20 graphs are drawn from the non-GHZ ones.

## 4. Random local Pauli Hamiltonians, ground energy (energy)

CHANGED from the transverse-field Ising chain. TFIM shares Hamiltonian
construction with the Ising-type tasks (40 of the 120) and its two builders
shared the one act where the construction errors live ("QUBO sign convention"
is one of the five method errors found here). Random Pauli sums are not a named
physical model.

- **Definition:** `H = sum_k c_k P_k`, n = 3..5 qubits, 2..5 distinct non-identity
  Pauli strings of weight <= 3, coefficients on a declared grid
  (multiples of 0.25 in [-2, 2], zero excluded), all stated in the statement.
  The Pauli label order follows the convention above and is the family's
  analogue of a boundary condition: it is declared, not left to either builder.
- **Oracle:** exact diagonalisation. Two independent constructions of the
  matrix: A, `SparsePauliOp.to_matrix()` with `eigvalsh`; B, hand-written 2x2
  matrices and an explicit kron in the declared order, with `eigsh`/dense.
- **Calibration, both builders must reproduce exactly:** a single term `c*P`
  has ground energy `-|c|`; a diagonal (all-Z/I) Hamiltonian has ground energy
  equal to the minimum over bitstrings, computed by direct enumeration.
- **Residual adjacency, disclosed:** it shares the energy oracle kind and the
  Pauli-sum / estimator skill with the 6 H2 tasks, and with the Ising tasks the
  skill of writing a Hamiltonian as Pauli terms. It is not the same Hamiltonian
  as either. See the held-out outcome below for which H2 task is held out.

## 5. Independent biased bits (distribution)

- **Oracle (closed form):** the product distribution, `kron` of `[1-p_i, p_i]`
  in the declared order (qubit 0 the last factor).
- **Construction:** RY(2 asin sqrt(p_i)) on qubit i, exact probabilities.
- n = 3, 4; 20 probability vectors.
- **The distribution verification path has never run on a real task.** Before it
  accepts any example it is validated on a hand-computed case, so a failure is
  never ambiguous between bad data and a bad checker. Hand case, n=2,
  `p = (0.25, 0.75)` (qubit 0 has p=0.25, qubit 1 has p=0.75):
  `P(k=0) = 0.1875, P(1) = 0.0625, P(2) = 0.5625, P(3) = 0.1875`. The checker
  must accept this and reject the bit-reversed vector
  (`P(1)` would read 0.5625). A loader path for the distribution kind also has
  to be added; the suite has none.

## The pilot is not the first 100 training examples

The modular adder shares its mechanism with the three reversible-adder test
tasks (and the Draper construction contains a QFT, a held-out family; see
below). Twenty constant-adder examples teach ripple-carry. Whether that is
leakage depends on the held-out reading and on `bench/heldout.yaml`: some
pilot data may have to be discarded or re-partitioned once the held-out list
is used for the real draw. The pilot measures whether the pipeline works,
nothing more.

## Held-out slice (`bench/heldout.yaml`, rule heldout-v1)

Seven families, 24 tasks, produced by the rule in that file (strata by oracle
kind, ascending sha256 of a fixed salt plus the family name, no reference to
any run's outcome); a test re-derives it from the task files.

| Family | Kind | Tasks |
|---|---|---|
| vqe_h2_r075 | energy | 2 |
| reversible_full_adder | unitary | 2 |
| qft | unitary | 6 |
| bell_phi_plus | statevector | 2 |
| bell_psi_plus | statevector | 2 |
| dj_balanced | statevector | 4 |
| qaoa_maxcut | statevector | 6 |

Covers unitary, statevector and energy. It cannot cover distribution: the suite
has no distribution task. Perturbation families present: all five. Both
canonical and perturbed tasks are in.

Consequences, stated rather than repaired:

- reversible_full_adder and qft are both neighbours of family 2 (ripple-carry
  and the QFT inside the Draper adder). Family 2 data is the first candidate for
  discard or re-partition.
- vqe_h2_r075 is held out, but vqe_h2_r055 and vqe_h2_r130 are not; family 4
  shares the energy kind with them.
- Expectation, registered with the list: the out-of-family slice will probably
  read the same before and after, and a null there bounds the claim; it does
  not fail it. The baselines are not zero: the 1.5B base (run F) passes
  qft_3q_perturbed, and the 7B (runs E and G) passes qaoa_maxcut_4q_perturbed,
  both in the slice, so the baseline is 1/24 for each, not 0/24.
  The rule did not use outcomes; the overlap was found after.
