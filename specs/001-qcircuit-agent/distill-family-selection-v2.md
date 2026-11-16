# Distillation: which families, recomputed under decision 2 (v2)

Status 2026-10-27. Computed, committed, nothing generated. Supersedes `distill-family-selection.md`
(v1, 2026-10-25), which stays in the repository as the record of what was concluded under the
family-held-out slice. Code: `src/qcagent/distill/skills.py` (`all_statements`, `histogram`),
`selection.py` (`CAPACITY_V2`, `FAMILY_SKILLS_V2`, `coverage_v2`); outputs `bench/skill_histogram.json`
(v2, 120 statements), `bench/family_selection_v2.json`; v1 histogram kept as
`bench/skill_histogram.v1-96-superseded.json`; tests `test_distill_skills.py`, `test_distill_selection.py`.

## Decision 2, recorded with its reason: the family-held-out slice is dropped

**Decision.** Reading (i) is restored: no shared statement and no shared answer between training and
test; training on the same family is allowed. The family-held-out slice (`heldout-v1`, `bench/heldout.yaml`)
is **superseded, not silently dropped**.

**Reason.** Filter (c), no mechanism identity with a held-out family, blocked training families for 64 of
the 96 in-family statements in v1. That is not a parameter to tune; it is the held-out design and useful
training in direct conflict. Applied strictly it yields a probably-null result on BOTH slices.

**What this changes, explicitly:**
- `heldout-v1` was chosen by a blind rule (a hash ordering, no reference to any outcome) BEFORE this
  consequence was known. A `heldout-v2` chosen now, with the consequence in view, would no longer be blind.
  So there is no v2; the slice is retired.
- The 24 tasks return to the test set. **Evaluation is on all 120.**
- The expectation registered with the list, that the out-of-family slice would probably read 0 versus 0 and
  that a null there bounds the claim rather than failing it, is **superseded by this discovery**: there is
  no out-of-family slice to read.
- The threshold registered for the headline claim (4 of 96 in-family, 7B on Ollama 0.40.8) is superseded the
  same way: on all 120 the 7B reads **5 of 120** (runs E and G, Ollama 0.40.8). A distilled 1.5B needs
  6 of 120 or more, on the same build, to beat it. *To be confirmed by the operator.*
- **The gates stay.** They are what holds the test set out at the statement and answer level, the standard
  position: lexical near-duplicate against EVERY test statement (reject at the median twin Jaccard 0.283,
  review from the cross-family 95th percentile 0.122), and strict circuit equivalence of every accepted
  circuit against all 120 references.
- **The final claim is bounded to:** oracle-verified synthetic data from the same distribution improves a
  small model on statements it has never seen. NOT out-of-family generalisation.

**The 64 of 96, as a finding.** In a domain whose canonical algorithm space is small, family-level holdout
and useful training are in direct conflict. Of the 96 in-family statements, 64 named a skill whose only
training family shared its mechanism with one of the 7 held-out families; the single most frequent skill
(the diagonal phase exp(-i gamma H), 40 statements) was blocked because the held-out QAOA is that circuit
plus a mixer. The held-out slice itself was drawn blind, and still ended up adjacent to most of what the
benchmark asks. That is a result about benchmark design (the suite covers the canonical algorithm space
densely), not an excuse.

## Step 0 (v2): the fairness boundary

The selection works from the STATEMENTS (the `prompt` field) of all 120 tasks, and from nothing else of
them: it never opens a reference circuit (a test spies on every file the code opens). Reference circuits are
benchmark-only; the project's rule is that whatever a real user would have is fair and whatever only the
benchmark has is not. The 120 references are used in one place, the post-generation circuit gate, which
EXCLUDES a training example whose circuit equals a reference; they play no part in choosing families.

**Consequence for the final claim.** The families are chosen from this benchmark's own statements, so the
result is bounded to "trained for this benchmark's distribution", not "general Qiskit improvement".

## Step 1: the skill histogram (120 statements)

Same method as v1 (regular expressions written from the data, one count per statement per skill; the
lexicon is code), plus three entries added after the 24 statements v1 never read were read (`qaoa_p1`,
`maxcut_graph`, `full_adder_majority`).

| rank | skill | statements | share | kind | what it is |
|---|---|---|---|---|---|
| – | no_measurement_return_state | 95 | 79% | format | statement format, not a skill (excluded from the ranking) |
| 1 | hadamard | 85 | 71% | construct | Hadamard gates (superposition layer, H on all or on a subset) |
| 2 | z_hamiltonian_pauli_sum | 49 | 41% | construct | a Hamiltonian written as a sum of Pauli-Z terms with coefficients |
| 3 | unitary_block_not_state | 47 | 39% | convention | a general-purpose unitary block, not a fixed starting state |
| 4 | diagonal_phase_evolution | 43 | 36% | construct | the diagonal phase exp(-i*gamma*H) of a Z-type Hamiltonian |
| 5 | single_qubit_rotation | 38 | 32% | construct | a single-qubit rotation with a stated angle (RY, RZ, P) |
| 6 | ancilla_register_layout | 34 | 28% | convention | an ancilla / input / output / counting register layout |
| 7 | restricted_gate_set | 33 | 28% | constraint | decomposition into a restricted gate set (use ONLY RZ, SX, X, CX ...) |
| 8 | xor_parity | 28 | 23% | construct | XOR / parity of bits |
| 9 | global_phase_tolerance | 27 | 22% | convention | equality 'up to global phase' |
| 10 | exact_ket_target | 25 | 21% | construct | a target state written as an explicit ket sum |
| 11 | linear_coupling_map | 24 | 20% | constraint | a linear (nearest-neighbour) coupling map, routing overhead, adjacency |
| 12 | oracle_construction | 24 | 20% | construct | building an oracle (CNOT / phase) for a given function |
| 13 | multi_body_z_string | 21 | 18% | construct | a many-body Z*Z*...*Z interaction term (parity phase) |
| 14 | qubit_order_reversal | 21 | 18% | convention | a reversed / relabelled qubit-ordering convention |
| 15 | controlled_phase | 20 | 17% | construct | controlled-phase / controlled-P rotations |
| 16 | compose_then_extra_gate | 19 | 16% | construct | a standard block followed by an additional gate / block |
| 17 | qft | 19 | 16% | algorithm | the Quantum Fourier Transform (textbook, or its inverse) |
| 18 | swap_layer | 18 | 15% | construct | a SWAP layer / reversal of qubits |
| 19 | ancilla_init_x_then_h | 16 | 13% | construct | initialise the ancilla to |1> with X, Hadamard on all |
| 20 | ghz_state | 14 | 12% | construct | GHZ-type state (full register or a subset of qubits) |
| 21 | hidden_bitstring_secret | 13 | 11% | construct | a hidden bit string / secret / period |
| 22 | maxcut_graph | 12 | 10% | construct | a MaxCut graph given by its edges |
| 23 | hadamard_on_subset_only | 11 | 9% | construct | Hadamard on a subset only (not the ancilla) |
| 24 | value_via_formula | 8 | 7% | convention | a parameter given by a formula, not a literal |
| 25 | bell_state | 7 | 6% | construct | Bell state |
| 26 | bernstein_vazirani | 6 | 5% | algorithm | Bernstein-Vazirani (hidden linear function) |
| 27 | deutsch_jozsa | 6 | 5% | algorithm | Deutsch-Jozsa |
| 28 | grover | 6 | 5% | algorithm | Grover search (phase oracle, diffuser, iteration count) |
| 29 | pauli_ground_energy | 6 | 5% | construct | ground-state energy of a Pauli-sum Hamiltonian |
| 30 | phase_estimation | 6 | 5% | algorithm | quantum phase estimation |
| 31 | qaoa_p1 | 6 | 5% | algorithm | a p=1 QAOA circuit (cost layer + RX mixer, fixed angles) |
| 32 | qubits_remain_zero | 6 | 5% | construct | some qubits stay in |0> (GHZ on a subset) |
| 33 | qubo_to_ising | 6 | 5% | construct | QUBO to Ising conversion (x = (1 - z) / 2) |
| 34 | reversible_boolean_logic | 6 | 5% | construct | reversible Boolean logic with Toffoli / multi-controlled X |
| 35 | simon | 6 | 5% | algorithm | Simon's algorithm (hidden period) |
| 36 | vqe_fixed_ansatz | 6 | 5% | algorithm | a fixed-parameter variational ansatz and its energy |
| 37 | w_state | 6 | 5% | construct | W state (equal superposition of Hamming-weight-1 states) |
| 38 | full_adder_majority | 4 | 3% | construct | a full / half adder with sum and carry |
| 39 | controlled_rotation_decomposition | 1 | 1% | construct | decomposition of a controlled rotation (CRY) into RY and CX |

## Step 2 (v2): a family per skill, with filter (c) gone

Filters kept: (a) a closed-form oracle, or two constructions with independent mechanisms; (b) at least 200
distinct parameter variations; (d) the oracle computes in bounded time at the qubit counts used (exact
diagonalisation is capped at 10 qubits; measured: 10 qubits 0.1 s, 11 qubits 0.6 s, 12 qubits 18.7 s, 13 a
1 GB matrix). Filter (c) no longer exists. With it gone, **every principal skill has a family that passes
(a), (b) and (d)**; the only skills without one are the non-separable ones (the Hadamard layer, global-phase
equality, the statement format), and the properties that are AXES on any family (restricted gate set, coupling
map, composition with an extra gate, a value given by formula, the unitary-level convention). The v1 finding
"a frequent skill with no verifiable family" was produced by (c), not by oracle-backed data.

| family | skills it is about (principal) | (a) oracle | (b) variations | (d) | new construction? |
|---|---|---|---|---|---|
| A qubit permutations | qubit_order_reversal, swap_layer | closed form (permutation matrix) | 5,905 (n <= 7) | ms | built |
| B graph / stabiliser / GHZ / Bell states | ghz_state, bell_state, qubits_remain_zero | closed form (amplitude formula) | 27,470 graphs (n 4..6) + subsets | ms | built (extended: GHZ class, Bell) |
| C Pauli-sum Hamiltonian energy | pauli_ground_energy, vqe_fixed_ansatz | two constructions + limit cases | 1.8e+20 (n 3..8) | n <= 10: 0.1 s | built |
| D independent biased bits | (secondary only: single_qubit_rotation) | closed form (analytic kron) | 1.2e+10 | ms | built |
| H diagonal Ising-phase circuits | diagonal_phase_evolution, z_hamiltonian_pauli_sum, multi_body_z_string, qubo_to_ising | closed form (diagonal unitary from the energy table) | 6.1e+18 | n <= 8: ms | new |
| K Bernstein-Vazirani / Deutsch-Jozsa | bernstein_vazirani, deutsch_jozsa | closed form (final state) | 2,035 (n <= 10) | ms | new |
| P QAOA p=1 | qaoa_p1, maxcut_graph | two constructions (CX-RZ-CX layers vs diagonal phase + RX tensor) | 2,747,400 | ms | new |
| Q QFT | qft | closed form (DFT matrix) | 502,512 | n <= 8: ms | new |
| W W / Dicke states | w_state | closed form | 87,425 (n >= 3) | ms | new |
| S Simon | simon | closed form (amplitudes) | 320 (n <= 6; 768 at n <= 7) | 12 qubits: ms | new |
| R reversible logic | reversible_boolean_logic, full_adder_majority | closed form (truth-table permutation) | 631,074 | n <= 9: ms | new |
| G Grover | grover | closed form (sin((2k+1) theta)) | 3,196,068 | n <= 10: ms | new |
| E QPE | phase_estimation | closed form (deterministic register) | 501 (n <= 8) | ms | new |

The capacities are upper bounds less the few instances the two gates will remove (a variation that is a test
task). Family "two-qubit ansatz energy" (the H2-like transcription, 6 statements) duplicates C's primary skill
and is not listed separately.

### What reaches the statements (the data the target decision needs)

A statement NEEDS the principal skills it names; it is FULLY reached when a chosen family teaches all of them,
PARTLY when it teaches at least one. (A statement that appends a QFT to an Ising circuit needs both.) Greedy by
statements newly made fully reached, after the four built families (which cost no new construction):

| step | family added | new constructions so far | statements FULLY reached | partly reached | capacity (distinct variations) | teaches (principal skills) |
|---|---|---|---|---|---|---|
| 0 | the four built (permutations, graph/stabiliser states, Pauli-sum energy, biased bits) | 0 | 18 | 55 | A 5,905; B 27,470; C ~1.8e20; D ~1.2e10 | qubit-order reversal, SWAP layer, GHZ / Bell / subset states, ground energy, VQE ansatz |
| 1 | diagonal_phase_ising | 1 | 55 (+37) | 90 | 6.14e+18 | diagonal_phase_evolution, multi_body_z_string, qubo_to_ising, z_hamiltonian_pauli_sum |
| 2 | kickback_bv_dj | 2 | 67 (+12) | 99 | 2,035 | bernstein_vazirani, deutsch_jozsa |
| 3 | qaoa_p1 | 3 | 78 (+11) | 101 | 2,747,400 | maxcut_graph, qaoa_p1 |
| 4 | qft | 4 | 90 (+12) | 101 | 502,512 | qft |
| 5 | w_dicke | 5 | 96 (+6) | 106 | 87,425 | w_state |
| 6 | simon | 6 | 102 (+6) | 111 | 320 | simon |
| 7 | reversible_logic | 7 | 108 (+6) | 116 | 631,074 | full_adder_majority, reversible_boolean_logic |
| 8 | grover | 8 | 114 (+6) | 120 | 3,196,068 | grover |
| 9 | qpe | 9 | 120 (+6) | 120 | 501 | phase_estimation |

The four built families, which the pilot chose by judgement, fully reach **18 of 120** statements
(15%) and partly reach 55. That is the honest size of what they cover; the v1 report's "touch 79
of 96" counted any skill named, and was generous. Secondary-skill reach per family (a convention or component the
family also exercises): qubit_permutation 33, stabilizer_graph_states 26, pauli_hamiltonian_energy 6, independent_biased_bits 38, diagonal_phase_ising 49, qft 22, kickback_bv_dj 43, qpe 31, simon 34, grover 24, w_dicke 6, reversible_logic 29, qaoa_p1 12, two_qubit_ansatz_energy 6.

## Step 3 (v2): the stop rule is NOT applied here

The target is not set (the operator sets it after this report). What this report gives instead is what the
target decision depends on: the reach curve above, and the ceiling that equal allocation imposes.

*Under equal allocation, a target T over k families needs T / k <= the smallest capacity among them.*

| families | last added | smallest capacity | limiting family | largest target under EQUAL allocation |
|---|---|---|---|---|
| 4 | independent_biased_bits | 5,905 | qubit_permutation | 23,620 |
| 5 | diagonal_phase_ising | 5,905 | qubit_permutation | 29,525 |
| 6 | kickback_bv_dj | 2,035 | kickback_bv_dj | 12,210 |
| 7 | qaoa_p1 | 2,035 | kickback_bv_dj | 14,245 |
| 8 | qft | 2,035 | kickback_bv_dj | 16,280 |
| 9 | w_dicke | 2,035 | kickback_bv_dj | 18,315 |
| 10 | simon | 320 | simon | 3,200 |
| 11 | reversible_logic | 320 | simon | 3,520 |
| 12 | grover | 320 | simon | 3,840 |
| 13 | qpe | 320 | simon | 4,160 |

Capacity is not binding for the built families or for the diagonal-phase family; it starts to bind at
Bernstein-Vazirani / Deutsch-Jozsa (2,035) and binds hard at Simon (320; 768 with n up to 7, more with other
oracle variants). The literal stop rule ("the fewest families that reach the target") stays degenerate for
small targets, because one family alone has more variations than any plausible target; a per-family ceiling
is a decision for the target step.

## Step 4: proportion

Equal allocation is the null hypothesis; any skew needs a reason recorded before generation, and cost is not a
reason (the full set is about $4 in any mix). Equal allocation over families whose capacities differ by ten
orders of magnitude over-samples the small ones (Simon at 320); that is the case for a ceiling, not for a skew.

## Step 5: adjacency against the test set

There are no slices any more, so adjacency is against the 120 test statements, from the histogram (statements
only). Strict = statements that name a principal skill of the family; generous = also a secondary skill (a
convention or component the family also exercises).

| family | statements about it (strict) | statements exercising a skill it also exercises (generous) |
|---|---|---|
| qubit_permutation | 33 | 33 |
| stabilizer_graph_states | 20 | 26 |
| pauli_hamiltonian_energy | 6 | 6 |
| independent_biased_bits | 0 | 38 |
| diagonal_phase_ising | 49 | 49 |
| qft | 19 | 22 |
| kickback_bv_dj | 12 | 43 |
| qpe | 6 | 31 |
| simon | 6 | 34 |
| grover | 6 | 24 |
| w_dicke | 6 | 6 |
| reversible_logic | 7 | 29 |
| qaoa_p1 | 12 | 12 |
| two_qubit_ansatz_energy | 6 | 6 |

**Leakage consequence of dropping the slice.** Training on the same family is now allowed, so the gates carry
the whole burden. Families whose test statements are templated (Bernstein-Vazirani, Simon, Grover, QFT, QPE,
QAOA, GHZ over a subset, the reversible circuits) will produce training statements lexically close to them if
they are phrased the same way; the lexical gate (reject at Jaccard 0.283 over word 5-grams) will reject near
copies, and the statements will have to be phrased differently (a teacher paraphrase of the structured spec,
not a template). That has to be run on the new statements before any family is generated at scale.

## Open decisions (none taken by me)

1. **The target** (statements or accepted examples), which the reach curve and the equal-allocation ceiling
   above are meant to inform.
2. **A per-family ceiling**, since capacity ranges from 320 to 10^19 and equal allocation over-samples the small.
3. **Which new constructions to build**, in the order of the reach curve: each costs an oracle and an
   independently checked construction (the diagonal-phase family reaches the most, 37 more statements fully).
4. **The headline threshold on all 120**: 6 of 120 or more, on Ollama 0.40.8 (superseded from 4 of 96).
5. **The sigma thresholds** (50% / 40%) were registered against the F baseline (sigma_error 65.3%); they are to be
   re-registered against the F-prime baseline BEFORE training, once F-prime is measured, and not re-based on
   `sigma_real` (see `distill-pilot-families.md`).

## Claim threshold, registered 2026-11-15 after the final base run and BEFORE the tuned run

**Final base run:** `results/a4949d939492f7f5` (`local-1.5b-rp`, digest `d7372fd82851`, Ollama 0.40.15, cold
cache), identical on 120/120 tasks to `results/9c9bf3fa94b7fe22` run the same day (status, every attempt's code,
error sequence; compared ignoring `hostname`, which differs between any two `docker run` containers).
`results/39c098084afdcfdc` is NOT a measurement (943/943 calls replayed from the response cache).

**Conditions that differ from the registration, declared:** the retrieval index has 1020 points, not the pinned
875 (`qdocs_points_gate: OVERRIDDEN` in every record). The training prompts were built on that same 1020-point
index (`data/train-v2.meta.json`), and base and tuned both run on it (owner's decision, 2026-11-15). These runs
are not comparable with the runs on 875. Server 0.40.15, not 0.40.8 (re-pin of 2026-11-12).

**Base, attempt-1 depth** (`analysis/cross_profile.py`; one task has no generator call and no depth):

| bin (strict) | n with an attempt | levels 0/1/2/3/4 | mean | compila@1 | sigma_code |
|---|---|---|---|---|---|
| all | 119 | 14/86/1/18/0 | 1.19 | 18 | 62/119 |
| 0 | 18 | 3/13/0/2/0 | 1.06 | 2 | 5/18 |
| 1 | 59 | 6/43/1/9/0 | 1.22 | 9 | 31/59 |
| 2+ | 42 | 5/30/0/7/0 | 1.21 | 7 | 26/42 |

**Threshold (owner, 2026-11-15):** an effect of training on attempt-1 depth is claimed only if the bootstrap 95%
interval of the paired change (tuned minus base, per task) lies above zero BOTH over all tasks AND in bin 2+.
No minimum effect size. Bootstrap: 10,000 resamples, seed 20261028, fixed in the code before the tuned run.

**Rule added here, not in the 2026-10-28 registration:** a task with no generator call on either side (planner
rejected or aborted) has no attempt 1 and is left out of the paired analysis, and listed.

**`SyntaxError` audit of the final base run:** one attempt-1 `SyntaxError` record in 120 tasks
(`CircuitError: 'register size error'`, sandbox-raised, level 1, correctly assigned). 0 misassigned; levels 0
and 1 are not merged. The base's 14 level-0 tasks come from `DeprecatedAPI` / `GenerationTruncated`.
