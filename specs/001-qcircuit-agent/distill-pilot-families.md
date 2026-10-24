# Distillation pilot: family specifications

Status: specification, 2026-10-24. Nothing here has generated data or spent
money. The pilot is FOUR families (1, 3, 4, 5), 80 statements. Family 2 was cut
(below); family 4 was changed from TFIM to random Pauli Hamiltonians.

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

## 2. Modular constant adder, modulus 2^n — CUT from the pilot

Not built now, not resolved against the held-out list. It is the phase-2
showcase for the double-builder discipline: it is the heaviest family to build
(ripple-carry with ancillas, Draper QFT, an arithmetic oracle, a strict
comparison of three objects), and its data could not be used for training,
because it shares its mechanism with held-out `reversible_full_adder` and
`qft`. The design is kept for phase 2:

- Oracle: `x -> (x + c) mod 2^n`, qubit 0 least significant; modulus fixed at
  2^n (arbitrary N would need machinery the constructions would share).
- Constructions: Cuccaro ripple-carry (ancillas, compared as the n-qubit block
  at ancilla |0>, ancillas verified returned to |0>) and Draper QFT; their
  failure modes (ancilla chaining, QFT loop direction) are two of the five
  method errors found in the 120 references.

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

## What "out-of-family" means

**Task-id family, not unseen mechanism.** A held-out family is one whose
task-id family no training statement may belong to. It does NOT mean that no
training statement shares a mechanism with it. The reason is a finding about
the benchmark: the 120 tasks cover the canonical algorithm space densely
enough that a held-out slice chosen by a blind rule is adjacent to almost any
training family. That is a property of the suite, not an error in the rule.
The final claim is therefore generalization at the statement level (no
training statement is a near-duplicate of, or from the same task-id family as,
a held-out task), which is weaker than "unseen mechanism" and well defined.

The pilot is not the first 100 training examples either: it measures whether
the pipeline works, nothing more; some pilot data may be discarded or
re-partitioned.

## Adjacency of each training family to the 24 held-out tasks

Adjacency is by mechanism or skill shared, not by task-id family (which is
zero for all, by construction).

| Training family | Adjacent held-out tasks | Count of 24 | Basis |
|---|---|---|---|
| 1 permutations | `qft_*` (3 + 3 perturbed: the final bit-reversal is a SWAP network), plus the other two `qubit_ordering`-perturbed tasks (`dj_balanced_6q_perturbed`, `reversible_full_adder_5q_perturbed`: "relabel qubit i as qubit n-1-i" is a qubit permutation) | 8 | the author's reading was "minimal"; corrected: 3 tasks are relabelling by construction, 8 with the QFT's SWAPs |
| 3 graph states | `bell_phi_plus_*`, `bell_psi_plus_*` (H plus a two-qubit entangler: 4), `qaoa_maxcut_*` (gates per graph edge: 6) | 10 | confirmed |
| 4 random Pauli ground energy | `vqe_h2_r075`, `vqe_h2_r075_perturbed` (same oracle kind, Pauli-sum Hamiltonian) | 2 firm; `qaoa_maxcut_*` (6) arguable, the cost operator is a Pauli sum although its oracle is a statevector | confirmed for the firm 2; up to 8 on the skill reading |
| 5 independent biased bits | none | 0 | RY product states and a distribution oracle; no held-out task has either |

A second adjacency matters more than these, and is not about the held-out
slice: see the threshold below. Half of the 7B's in-family successes are H2
energy tasks, the kind family 4 targets.

## Family 5 cannot move the benchmark

The suite has no distribution task, so family 5's 20 examples have no
corresponding test tasks. It stays in the pilot because it is the first
exercise of the distribution verification path. For scaling it has the lowest
measurable return, and the reason is a gap in the suite, not in the family.

## Registered before any training: baselines and the headline threshold

Same-slice successes of the baselines the distilled 1.5B will be compared with
(one seed per run; every figure carries its server build). Slice =
`bench/heldout.yaml` (24 tasks); in-family = the other 96.

| Run | Model | Build | In-family (of 96) | Held out (of 24) | Total |
|---|---|---|---|---|---|
| C | 7B | 0.35.1 | 7 | 0 | 7 |
| E | 7B | 0.40.8 | **4** | 1 | 5 |
| G (repeat of E) | 7B | 0.40.8 | **4** | 1 | 5 |
| F | 1.5B | 0.40.8 | 0 | 1 | 1 |

- 7B in-family successes (E and G, same tasks): `vqe_h2_r055`,
  `vqe_h2_r130_perturbed`, `ghz_linear5_mixed`, `ghz_linear5_scattered_even`.
  Held out: `qaoa_maxcut_4q_perturbed`.
- 1.5B (F): in-family 0/96, held out 1/24 (`qft_3q_perturbed`). Confirmed.
- **THRESHOLD: 4/96 on the in-family slice, on Ollama 0.40.8.** A distilled 1.5B
  must beat it, on the same slice and the same build, to support "a 1.5B
  outperforms a 7B": that means 5/96 or more. Written down here before training.
- Two properties of this threshold, stated now: (a) two of its four tasks are
  H2 energy tasks, the oracle kind family 4 is built on, and the other two are
  GHZ tasks, which the pilot does not train on; a gain through the energy tasks
  would be real but narrow. (b) A margin of one task is the smallest difference
  this suite can show; it is deterministic on a fixed build (run G repeated E
  with 0/120 differences) but says little about a new build.
- **Held-out slice expectation, registered with it:** it will probably read the
  same before and after (the baselines are 1/24 for the 7B and for the 1.5B,
  not 0/24), and a null there bounds the claim rather than failing it.

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

Covers unitary, statevector and energy; it cannot cover distribution, because
the suite has no distribution task. All five perturbation families are present,
canonical and perturbed both.

**The list is not changed by anything found after the rule ran.** Consequences
discovered afterwards (the adjacencies above, the overlap with known baseline
successes, the cut of family 2) are disclosures. A list that moves once the
results are known makes the hash ordering meaningless; a failure is reported,
not repaired by swapping. The overlap found after the rule ran:
`qft_3q_perturbed` (1.5B, F) and `qaoa_maxcut_4q_perturbed` (7B, E and G) are in
the slice. `vqe_h2_r055` and `vqe_h2_r130` are not held out, and the 7B passes
both.
