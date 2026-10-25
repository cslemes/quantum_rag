# Distillation: which families, computed from the data

Status 2026-10-25. Computed, committed, nothing generated. Code: `src/qcagent/distill/skills.py`
(histogram), `selection.py` (capacities, timings); outputs `bench/skill_histogram.json`,
`bench/family_selection_capacity.json`; tests `test_distill_skills.py`, `test_distill_selection.py`.

## Step 0: the fairness boundary (recorded first)

The selection works only from the STATEMENTS (the `prompt` field) of the 96 in-family tasks.
It never opens a reference circuit, and it never reads any of the 24 held-out tasks: those files
are skipped by name before they are opened, and a test spies on every file the code opens.
Reference circuits are benchmark-only; the project's rule is that whatever a real user would have
is fair and whatever only the benchmark has is not. Choosing families from the held-out tasks would
let the held-out slice influence training.

The held-out FAMILY NAMES (`bench/heldout.yaml`) are used for exactly one thing: filter (c), mechanism
identity, judged from the textbook definition of each family. No held-out statement or reference is read.

**Consequence for the final claim.** The families are chosen from this benchmark's own in-family
statements, so the result is bounded to "trained for this benchmark's distribution", not "general
Qiskit improvement".

## Step 1: the skill histogram (96 in-family statements)

A skill is a construct, API surface, convention or constraint that a statement names or asks for.
The lexicon is a list of regular expressions, written from the data (it started from the document
frequency of the statements' terms, then from reading all 96); a statement counts once per skill. The
lexicon is where judgement enters, which is why it is code in the repository, and re-runnable.

| rank | skill | statements | share | kind | what it is |
|---|---|---|---|---|---|
| – | no_measurement_return_state | 74 | 77% | format | statement format, not a skill (excluded from the ranking) |
| 1 | hadamard | 68 | 71% | construct | Hadamard gates (superposition layer, H on all or on a subset) |
| 2 | z_hamiltonian_pauli_sum | 44 | 46% | construct | a Hamiltonian written as a sum of Pauli-Z terms with coefficients |
| 3 | unitary_block_not_state | 41 | 43% | convention | a general-purpose unitary block, not a fixed starting state |
| 4 | diagonal_phase_evolution | 40 | 42% | construct | the diagonal phase exp(-i*gamma*H) of a Z-type Hamiltonian |
| 5 | restricted_gate_set | 30 | 31% | constraint | decomposition into a restricted gate set (use ONLY RZ, SX, X, CX ...) |
| 6 | ancilla_register_layout | 29 | 30% | convention | an ancilla / input / output / counting register layout |
| 7 | global_phase_tolerance | 24 | 25% | convention | equality 'up to global phase' |
| 8 | linear_coupling_map | 24 | 25% | constraint | a linear (nearest-neighbour) coupling map, routing overhead, adjacency |
| 9 | single_qubit_rotation | 23 | 24% | construct | a single-qubit rotation with a stated angle (RY, RZ, P) |
| 10 | exact_ket_target | 20 | 21% | construct | a target state written as an explicit ket sum |
| 11 | oracle_construction | 20 | 21% | construct | building an oracle (CNOT / phase) for a given function |
| 12 | xor_parity | 20 | 21% | construct | XOR / parity of bits |
| 13 | multi_body_z_string | 18 | 19% | construct | a many-body Z*Z*...*Z interaction term (parity phase) |
| 14 | qubit_order_reversal | 16 | 17% | convention | a reversed / relabelled qubit-ordering convention |
| 15 | ghz_state | 14 | 15% | construct | GHZ-type state (full register or a subset of qubits) |
| 16 | compose_then_extra_gate | 13 | 14% | construct | a standard block followed by an additional gate / block |
| 17 | ancilla_init_x_then_h | 12 | 12% | construct | initialise the ancilla to |1> with X, Hadamard on all |
| 18 | controlled_phase | 12 | 12% | construct | controlled-phase / controlled-P rotations |
| 19 | hidden_bitstring_secret | 12 | 12% | construct | a hidden bit string / secret / period |
| 20 | qft | 11 | 12% | algorithm | the Quantum Fourier Transform (textbook, or its inverse) |
| 21 | swap_layer | 10 | 10% | construct | a SWAP layer / reversal of qubits |
| 22 | hadamard_on_subset_only | 7 | 7% | construct | Hadamard on a subset only (not the ancilla) |
| 23 | bernstein_vazirani | 6 | 6% | algorithm | Bernstein-Vazirani (hidden linear function) |
| 24 | grover | 6 | 6% | algorithm | Grover search (phase oracle, diffuser, iteration count) |
| 25 | phase_estimation | 6 | 6% | algorithm | quantum phase estimation |
| 26 | qubits_remain_zero | 6 | 6% | construct | some qubits stay in |0> (GHZ on a subset) |
| 27 | qubo_to_ising | 6 | 6% | construct | QUBO to Ising conversion (x = (1 - z) / 2) |
| 28 | simon | 6 | 6% | algorithm | Simon's algorithm (hidden period) |
| 29 | value_via_formula | 6 | 6% | convention | a parameter given by a formula, not a literal |
| 30 | w_state | 6 | 6% | construct | W state (equal superposition of Hamming-weight-1 states) |
| 31 | reversible_boolean_logic | 5 | 5% | construct | reversible Boolean logic with Toffoli / multi-controlled X |
| 32 | pauli_ground_energy | 4 | 4% | construct | ground-state energy of a Pauli-sum Hamiltonian |
| 33 | vqe_fixed_ansatz | 4 | 4% | algorithm | a fixed-parameter variational ansatz and its energy |
| 34 | bell_state | 3 | 3% | construct | Bell state |
| 35 | deutsch_jozsa | 2 | 2% | algorithm | Deutsch-Jozsa |
| 36 | controlled_rotation_decomposition | 1 | 1% | construct | decomposition of a controlled rotation (CRY) into RY and CX |

## Step 2: a family per skill, top down

Filters: (a) a closed-form oracle, or two constructions with independent mechanisms; (b) at least 200
distinct parameter variations (computed, in the declared qubit range); (c) no mechanism identity with a
held-out family; (d) the oracle computes in bounded time at the qubit counts used.

**Filter (c), the operational reading (it moves the list more than any other decision).** Identity when
(i) one is a parameter specialisation of the other (BV is DJ-balanced with a linear oracle; QAOA with
beta = 0 is H plus the cost layer), or (ii) the candidate's construction contains a held-out family's
WHOLE construction at 3 or more qubits (the Draper adder contains the QFT; ripple-carry contains the full
adder). A shared primitive (one H and one CX) or an overlapping skeleton is ADJACENCY: reported, not
disqualifying.

**Filter (d), measured.** Exact diagonalisation of a Pauli-sum Hamiltonian (`SparsePauliOp.to_matrix` +
`eigvalsh`, this host): 8 qubits 0.009 s,
10 qubits 0.098 s,
11 qubits 0.569 s,
12 qubits 18.701 s (33x the step before, and 13 qubits
is a 1 GB matrix): the wall is at 12. Energy is capped at 10 qubits. The unitary oracles (128 x 128 at 7 qubits),
state oracles (up to 12 qubits) and distributions are not time-limited at the sizes used.

Families are named A to D (the four built) and E to G (candidates not built).
A = qubit permutations (unitary); B = graph / stabiliser states, extended to GHZ's class and to subset-GHZ
targets (statevector); C = random Pauli Hamiltonian ground energy (energy); D = independent biased bits
(distribution); E = Simon; F = Grover; G = W / Dicke states.

| rank | skill (n) | candidate | (a) | (b) variations | (c) | (d) | verdict |
|---|---|---|---|---|---|---|---|
| 1 | hadamard (68) | none: a component of every construction | n/a | n/a | n/a | n/a | SKIP: not separable; taught implicitly by every family |
| 2 | z_hamiltonian_pauli_sum (44) | C | yes (two constructions + limit cases) | 1.78e+20 | adjacency only (vqe_h2_r075: its task transcribes a fixed ansatz) | n <= 10: 0.1 s | PASS, built. Partial: C reads a Pauli-sum spec for a ground-state task, the statements use it for phase evolution |
| 3 | unitary_block_not_state (41) | A (unitary oracle kind) | yes (closed form) | 5905 | adjacency (qft's swap layer) | n <= 7: ms | PASS, built (partial: the unitary-level convention) |
| 4 | diagonal_phase_evolution (40) | diagonal Z-phase circuits, H then exp(-i gamma H) | yes (diagonal closed form) | unbounded | **IDENTITY with qaoa_maxcut**: QAOA with beta = 0 is exactly this | fine | **SKIP (c)** |
| 5 | restricted_gate_set (30) | an AXIS: allowed-gate check on top of any admissible family | yes (base oracle + gate set) | multiplies the base | inherits the base | fine | PASS as an axis on A, B (no new construction) |
| 6 | ancilla_register_layout (29) | E (Simon): input / output registers | yes (closed-form amplitudes + independent simulation) | 320 (n <= 6; 768 at n <= 7) | adjacency (H-oracle-H skeleton shared with DJ) | 12 qubits | PASS, **new construction**; the next unused skill |
| 7 | global_phase_tolerance (24) | none: a property of the verifier | n/a | n/a | n/a | n/a | SKIP: not separable (the strict check forgives exactly a global phase) |
| 8 | linear_coupling_map (24) | an AXIS over B: the existing topology check on a linear map | yes (B's closed form; depth budget from B's own construction) | multiplies B | adjacency | fine | PASS as an axis |
| 9 | single_qubit_rotation (23) | D (angle 2 asin sqrt p) | yes (analytic kron) | 1.17e+10 | none | fine | PASS, built (partial) |
| 10 | exact_ket_target (20) | B (amplitude formula) | yes (closed form) | 27470 | adjacency (Bell, qaoa_maxcut) | n <= 6: ms | PASS, built |
| 11 | oracle_construction (20) | E (Simon), F (Grover); BV / DJ excluded | yes | E 320, F 3,196,068 | BV / DJ: identity with dj_balanced | fine | PASS via E, F (new); BV / DJ SKIP (c) |
| 12 | xor_parity (20) | BV, reversible parity, Z-string parity phase | – | – | each is identity: dj_balanced, reversible_full_adder, qaoa_maxcut | – | **SKIP (c)** |
| 13 | multi_body_z_string (18) | as 4 | – | – | as 4 | – | **SKIP (c)** |
| 14 | qubit_order_reversal (16) | A | yes | 5905 | adjacency (qubit_ordering-perturbed held-out tasks) | ms | PASS, built (partial: A builds the permutation, the statements ask to re-index a construction) |
| 15 | ghz_state (14) | B extended to GHZ-class and subset targets (|S| >= 3) | yes (closed form) | 27470 graphs + subsets | adjacency (Bell is a primitive; |S| = 2 excluded) | fine | PASS, built (raising variations) |
| 16 | compose_then_extra_gate (13) | an AXIS: compose an admissible block with an extra gate | yes (product of oracles) | multiplies | blocks restricted to admissible families | fine | PASS as an axis |
| 17 | ancilla_init_x_then_h (12) | phase kickback: instances are DJ, BV, QPE | – | – | identity: dj_balanced, qft | – | **SKIP (c)** |
| 18 | controlled_phase (12) | diagonal phases / QFT blocks | – | – | identity: qft, qaoa_maxcut | – | **SKIP (c)** |
| 19 | hidden_bitstring_secret (12) | E (Simon); BV excluded | yes | 320 | BV: identity with dj_balanced | 12 qubits | PASS via E (new) |
| 20 | qft (11) | the QFT | – | – | identical to held-out qft | – | **SKIP (c)** |
| 21 | swap_layer (10) | A | yes | 5905 | adjacency (qft) | ms | PASS, built |
| 22 | hadamard_on_subset_only (7) | E (Simon) | yes | 320 | adjacency | fine | PASS via E (new) |
| 23 | bernstein_vazirani (6) | BV | yes | – | **identity: specialisation of dj_balanced** | – | **SKIP (c)** |
| 24 | grover (6) | F | yes (closed form, sin((2k+1) theta)) | 3,196,068 | none | n <= 10: ms | PASS, new construction |
| 25 | phase_estimation (6) | QPE | – | – | contains the whole QFT | – | **SKIP (c)** |
| 26 | qubits_remain_zero (6) | B (subset GHZ) | yes | as 15 | adjacency | fine | PASS, built |
| 27 | qubo_to_ising (6) | needs a circuit equal to a diagonal phase | – | – | as 4 (MaxCut is a QUBO) | – | **SKIP (c)** |
| 28 | simon (6) | E | yes | 320 | adjacency | 12 qubits | PASS, new |
| 29 | value_via_formula (6) | an AXIS: statement style | yes | multiplies | inherits | fine | PASS as an axis |
| 30 | w_state (6) | G (weighted W / Dicke, n >= 3) | yes (closed form) | 87,425 | adjacency (Bell psi+ at n = 2: excluded) | fine | PASS, new construction |
| 31 | reversible_boolean_logic (5) | Boolean functions into ancillas | – | – | contains / specialises reversible_full_adder | – | **SKIP (c)** |
| 32 | pauli_ground_energy (4) | C | yes | as 2 | adjacency | fine | PASS, built |
| 33 | vqe_fixed_ansatz (4) | C (partial) | yes | as 2 | adjacency (vqe_h2_r075) | fine | PASS, built (partial) |
| 34 | bell_state (3) | Bell | – | – | identical to held-out bell_* | – | **SKIP (c)** |
| 35 | deutsch_jozsa (2) | DJ | – | – | identical class as dj_balanced | – | **SKIP (c)** |
| 36 | controlled_rotation_decomposition (1) | a component of G | – | – | – | – | below any threshold |

### What the filters cost: the finding

**64 of the 96 in-family statements name at least one skill whose only training family is blocked by (c).**
The most frequent real skill after the Hadamard layer, the diagonal phase exp(-i gamma H) (40 statements,
42%), has a closed-form oracle and unlimited variations, and is out for one reason: the held-out
qaoa_maxcut is that circuit plus a mixer, so a family teaching it teaches the held-out cost layer. The
same wall takes the Z-string phases, QUBO to Ising, controlled phases, the QFT and QPE, Bernstein-Vazirani
and Deutsch-Jozsa, reversible logic, and Bell. This is the density of the benchmark showing again (the
held-out slice, drawn blind by a hash rule, is adjacent to most of what the benchmark asks), and it is a
limit of oracle-backed data: a frequent skill with no verifiable family. Hamiltonian time evolution came
out of the histogram (rank 4) and then out of the filter; it stays out.
**If the operator reads (c) more narrowly** (identity only when the held-out construction is contained
whole), the diagonal-phase family passes and becomes the largest addition: 40 + 18 + 6 statements. The
price is stated: it teaches the cost layer of 6 of the 24 held-out tasks.

## Step 3: the stop rule

The target is a stated assumption: **5,000 statements** (the figure the cost estimate used).

*Literally applied, the rule is degenerate:* capacity is not the binding constraint. Family C alone has
1.78e+20 distinct variations, so the walk reaches the target at rank 2 with ONE
family. Counting capacity cannot decide how many families are needed; it would need a per-family ceiling,
which I have not invented.

*Applied as the note says* ("variations are nearly free; prefer raising variations over adding families"):
the walk down the ranked list assigns every admissible skill to a family, and the four built families, with
B extended to GHZ's class and subset targets and the three axes (restricted gate set, coupling map,
composition), already take **every admissible skill down to rank 21 except those that need E, F or G**. Under
equal allocation each family gets 1,250 statements, below the smallest capacity (A: 5,905). **New
constructions needed to reach the target: zero.**

**Where it stops, and the next unused skill.** It stops before rank 6, `ancilla_register_layout` (29
statements): the first admissible skill the four built families do not teach. It needs E (Simon):
closed-form amplitudes plus an independent statevector simulation, 320 variations at 12 qubits. After E,
the next are F (Grover, rank 24, 6 statements) and G (W / Dicke, rank 30, 6). E, F and G together reach
7 more in-family statements than the built four plus the blocked skills do.

*Honest limit of "teaches".* Coverage of a skill by a built family is mostly PARTIAL, marked in the table:
C reads a Pauli-sum Hamiltonian but for a ground-state task; D computes a rotation angle from a target
amplitude, not a stated one; A builds a permutation where the statements ask to re-index a construction.
That the four families the pilot chose by judgement turn out to touch 79 of the 96 statements' skills (89
with the axes) is the data's answer; it is not the same as saying they teach those skills fully.

## Step 4: proportion

Equal allocation, **1,250 statements per family** (A, B, C, D) at a 5,000 target. No skew is proposed, so
no reason has to be recorded. Cost is not a reason: the full set is about $4 in any mix (it follows the
family mix, the energy family being the expensive one, and the price is noise at this scale). Variation
ranges used: A n = 3..7; B connected graphs n = 4..6; C n = 3..8 (energy oracle capped at 10 qubits);
D n = 3..8.

## Step 5: adjacency of the final families, against both slices

In-family adjacency = in-family statements that name a skill the family covers (from the histogram, so from
statements only). Held-out adjacency is by mechanism, from the family tables recorded earlier.

| family | in-family statements adjacent (of 96) | held-out tasks adjacent (of 24) |
|---|---|---|
| A permutations (+ restricted gate set, composition axes) | 23 (qubit_order_reversal 16, swap_layer 10) | 8 (qft's swap layer 6; the other two qubit_ordering-perturbed tasks 2) |
| B graph / stabiliser states incl. GHZ class (+ coupling-map axis) | 21 (ghz_state 14, qubits_remain_zero 6, exact_ket_target 20) | 10 (Bell x4, qaoa_maxcut x6) |
| C Pauli-sum Hamiltonian energy | 44 (the Pauli-sum Hamiltonian is named in 44; the ground-energy task in 4) | 2 firm (vqe_h2_r075 and its twin); 6 arguable (qaoa_maxcut, Pauli-sum cost operator) |
| D independent biased bits | 23 (single_qubit_rotation) | 0 |
| union of the four | 79 of 96 (89 with the three axes) | |

**Changes the data forced:** family B now includes GHZ's local-Clifford class and subset-GHZ targets
(excluded in the pilot because GHZ was one of the two largest in-family families; the histogram ranks
`ghz_state` 15th with 14 statements). The consequence is a leakage one: statements for GHZ over a qubit
subset will sit close to the 14 GHZ test statements, and the gate's lexical measure may reject many; that is
what the gate is for, and it has to be run on the new statements.

## Open decisions (none was taken by me)

1. **Filter (c)**, the reading above. It decides whether the largest block of the benchmark is trainable.
2. **The target**, assumed at 5,000 statements.
3. **The stop rule** is degenerate without a per-family ceiling; a ceiling is a decision.
4. **Whether to add E (Simon)**, the next unused skill, at the price of two independent implementations.
5. **GHZ in family B** and its leakage cost.
