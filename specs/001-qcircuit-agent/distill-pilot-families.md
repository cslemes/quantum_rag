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

> **SUPERSEDED 2026-10-27 (decision 2): the sections "What out-of-family means", "Adjacency of each
> training family to the 24 held-out tasks", "Registered before any training: baselines and the headline
> threshold" (its slice split and its 4/96 threshold) and "Held-out slice" describe the family-held-out
> slice `heldout-v1`, which was dropped. The 24 tasks return to the test set and evaluation is on all 120.
> They are kept as the record. The decision, its reason and what replaces them are in
> `distill-family-selection-v2.md`. The headline threshold becomes 5 of 120 for the 7B on Ollama 0.40.8
> (runs E and G): a distilled 1.5B needs 6 of 120 or more on the same build, to be confirmed.**

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

## Prediction registered before any training: repair sensitivity (2026-10-25, criterion restated the same day)

**Headline: the prompt changes and the outcome does not.** In run F (1.5B base,
Ollama 0.40.8, one seed), 77 of the 118 failures that generated code (65.3%) carry
the identical error (stage, type and message) in all five attempts, and in 71 of
those 77 the critic's hint took 2 or 3 distinct values across the attempts (62 with
two, 9 with three; 6 with one). The input to the next attempt varied; the error did
not. This is stronger than "the system repeats itself": the critic's prompt is task,
error, error message and the generated CODE, a different hint means a different
prompt (a repeated prompt is answered identically, and in a run the response cache
returns the stored text), and so in these runs the generator did change its code,
while the error stayed constant. (F's own cache hit rate was not recorded, so this
inference rests on the design of the cache and on determinism, not on a count.)

**`sigma` is an UPPER BOUND, and why.** The records hold identical ERRORS, not
identical code. The error taxonomy is closed, hence lossy by construction: different
code collapses into the same error record. That is the property that invalidated the
token-count test (chapter 6, section 6.5), and the hint observation above already
shows it at work. Until the code hash below exists, every `sigma` computed from
records is `sigma_error >= sigma_code`.

**Making it exact, before the two 1.5B runs.** The trace now persists, per
generation, a hash of the extracted code (`code_sha256_16`), how it was extracted
(`code_extraction`: `fenced` or `raw_fallback`) and the output tokens. Additive: no
behaviour changes, the extracted code is byte-for-byte what it was, and comparability
with C to G is kept (any trace equality across the change must ignore the three new
keys). `sigma_code` = failures whose five attempts have the same code hash / failures
that generated code. By construction `sigma_code <= sigma_error`.

**Definitions** (same suite, same build, one seed): `C` = `compila@1` (count of 120),
`S` = success (count of 120), `sigma` = the stuck fraction, `kappa` = `S / C`.
**Baseline F:** `C0` = 10, `S0` = 1, `sigma_error0` = 65.3% (77/118). `sigma_code0`
will be measured in the two 1.5B base re-runs that precede training.

**Prediction, built on `sigma`, the only one of the measures with a sample (118
failures in the denominator; `S` has one success in its numerator).** "C rises"
means `C1 >= 20` (a doubling of `C0`; my operationalisation, to be confirmed before
training).
- **Predicted:** `C` rises and `sigma` stays at or above 50%. Phase 1 improves first
  attempts without improving repair, so a better first attempt still enters a loop
  that does not recover; that is why phase 1 may not move the end-to-end number much.
- **Refuted:** `C` rises and `sigma` falls to 40% or below. Repair improved without
  repair data, so phase 2's premise is wrong.
- **Ambiguous:** `sigma` between 40% and 50%.
- **Which `sigma`.** `sigma_code` of the phase-1 run decides, when available.
  Because `sigma_error` is an upper bound, `sigma_error <= 40%` is a conclusive
  refutation on its own; `sigma_error >= 50%` is only necessary for "predicted".
  If `sigma_error >= 50%` but `sigma_code < 50%`, the outcome is ambiguous (the bound
  was too loose to decide).
- **`kappa` and all raw counts are reported alongside as description, never as a
  criterion.** The first version of this registration used `kappa < 0.10` and it was
  wrong: `C` from 10 to 40 with `S` from 1 to 3 gives `kappa` = 0.075, which would
  "confirm" a tripling of success. (The first version also read a fall of `sigma` as
  "untested", which is backwards: `sigma` falling IS the prediction failing.)

**DECISION 2026-10-27 on the finding below.** The sigma thresholds are NOT re-based on
`sigma_real`: that treats the symptom. The fix is to re-measure on a sane configuration (F-prime,
registered below) and let `sigma` mean what it was meant to mean. The split `sigma_trunc` /
`sigma_real` stays as a REPORTING dimension, being the diagnostic that found this. The 50% / 40% lines were
registered against F's `sigma_error` of 65.3%; they are to be re-registered against F-prime's measured
baseline BEFORE any training, and never after seeing the trained model. The generator now also labels a
truncated generation `GenerationTruncated` instead of a syntax error (chapter 6, section 6.3), so
`sigma_error` of the runs from F-prime on no longer counts a truncation as a repeated syntax error.

**FINDING that bears on the criterion, found while restating it (superseded by the decision above).** Of the 77 stuck failures in F, **51 are one mode**: the final
code is the raw text starting with an unclosed opening fence, ends mid-sentence in a
repetition loop ("Apply the phase oracle one last time ...") and the error is
`invalid syntax (<unknown>, line 1)`. These runs spent a mean of 21,055 output tokens
(5 attempts at about the 4,096-token cap), against 2,239 for the other F runs. The
generation degenerates into repetition until the cap, the closing fence is never
written, and `_extract_code` falls back to the raw text. It is a truncation, labelled
`SyntaxError` by the catch-all (chapter 6, section 6.6), not a circuit error and not
evidently a repair-prompt insensitivity; it also feeds the truncated code back as the
"previous attempt". The same error text is the attempt-1 error of 51 of the 120 F runs
and of 259 of F's 346 static `SyntaxError` records (verified as unclosed-fence
truncation for the 51 stuck runs only). Consequences: (1) `sigma` is mostly one mode,
and phase 1 (short, fence-closing teacher outputs) can make it fall as a side effect,
which would read as "refuted" under the criterion above without any repair
improvement; (2) among failures that are NOT this truncation, the stuck fraction at
baseline is 26 of 67 = 38.8%, already below the 40% line. So the criterion cannot be
applied to `sigma_all` with these thresholds without deciding whether it measures
repair or truncation. (The proposal made at the time, to re-base the thresholds on `sigma_real`, was
declined: see the decision above.)

**Two limits, stated now.** The critic that writes the hint is the same 1.5B, so
"repair sensitivity" is the generator-plus-critic pair, not the generator alone. The
conversion `kappa0` (1 of 10) is fragile (Wilson 95% 1.8% to 40.4%); this is a further
reason `kappa` is description only. (Superseded 2026-10-27: the result is reported on all 120 tasks; there is no
held-out slice.)

## Prediction registered before running F-prime (2026-10-27)

**F-prime** is the 1.5B with a repetition penalty (profile `local-1.5b-rp`, config
`config.local-1.5b-rp.yaml`), run on the same suite, build (Ollama 0.40.8), protocol and seed as F. **F stays
as it is**: it is the config-matched comparison against E, and the scale claim in chapter 5 rests on it. F-prime
is the distillation baseline. Each comparison uses the arm that matches it.

*What differs between F and F-prime, stated so that nothing is hidden:* (1) `repeat_penalty` 1.1 and
`repeat_last_n` 64, sent explicitly (F sent neither; an unsent `repeat_penalty` on this build is equivalent to
1.0, measured); a repetition penalty is a deterministic transform of the logits from the generated prefix, so
`temperature` 0 stays reproducible, and it is part of the model's identity (a new profile, a new cache key).
(2) The generator's code change of the same day: a response that reaches the 4,096-token cap WITHOUT closing
its code fence is labelled `GenerationTruncated` and not executed, instead of being executed and labelled a
syntax error. The two changes are made together because the second records what the first removes; their
separate contributions to F-prime are not separable in a single run (the label only matters for the attempts
that still truncate), and the trace records every truncated attempt (`generation_truncated`,
`output_tokens`, `code_sha256_16`).

*Why 1.1.* Chosen on a validation set that is not the test set: the 80 pilot statements through the bare
generator prompt, by a rule fixed before the 1.2 and 1.3 results were seen (the smallest penalty that maximises
the number of executed programs). Measured: penalty 1.0 gave 15 of 80 generations at the token cap, 5 of 80
programs executed; 1.1: 2 and 56; 1.2: 1 and 30; 1.3: 2 and 10. (Oracle-accepted: 0, 0, 1, 0 of 80, so the
validation set does not discriminate on correctness; the 1.5B does not solve these statements at any penalty.)
That probe used the bare prompt (no retrieval context, no planner), so it does not predict the pipeline.

**Prediction (the operator's, registered before the run):** the degeneration mode largely disappears, so most
of F's 51 truncation failures become ordinary failures; `sigma_error` falls toward the 38.8% measured for
non-truncation failures; and success rises modestly, **2 to 5 of 120**. **If success exceeds 10 of 120, the
1.5B baseline was dominated by decoding rather than capability, and the whole 1.5B narrative in chapter 5
(the scale claim, the `compila@1` of 10 of 120, the 1 of 120) needs rewriting.**

*Added by me, same registration:* the validation probe moved executability from 5 of 80 to 56 of 80, so a large
rise in `compila@1` (F: 10 of 120) is expected, and the branch "success above 10 of 120" is less remote than
the 2-to-5 point estimate suggests. Reported with it: `compila@1`, `sigma_error`, `sigma_trunc` and `sigma_real`
(`sigma_real` as the share of failures that are stuck and not truncations), the count of
`GenerationTruncated` attempts, and success on all 120.

## Held-out slice (`bench/heldout.yaml`, rule heldout-v1) — SUPERSEDED 2026-10-27

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

## Built (2026-10-24; nothing generated, nothing spent)

Code: `src/qcagent/distill/strict.py`, `families/` (four families), `gate.py`;
tests `tests/unit/test_distill_{strict,families,distribution_path,gate}.py`.

- **Strict equivalence** (`strict.py`): global phase forgiven, nothing else; no
  reversal or permutation search. Tests: a bit-reversed circuit and a bit-reversed
  state are reported NOT equivalent; the QFT without its swaps is not the QFT.
  Training-data acceptance uses it for unitary and statevector families; the
  cascade's endianness-tolerant checks are not used on training data.
- **Four families, 80 variations**, each with oracle and construction agreeing
  and a test that a wrong construction is caught (the reversed swap order for
  permutations). Graph states: the GHZ local-Clifford class is enumerated (38
  connected graphs on 4 vertices, 5 in the class; 728 on 5, 6 in the class);
  10 graphs per size are drawn round-robin over isomorphism classes.
- **Family 4, what the label order does and does not decide.** The ground energy
  is a spectrum, invariant under relabelling the qubits, so the oracle value
  cannot disagree between builders because of endianness, and the limit-case
  calibration (30 checks) would not catch a reversal either. The order decides
  which STATE reaches the energy, and is exercised where a state is involved: the
  reference circuit must pass the cascade's `check_energy`, and a teacher's
  circuit is judged by the expectation of H under the declared label order.
  (The earlier wording "label order is this family's endianness" holds for the
  state, not for the energy.)
- **Family 5 and the distribution path.** The cascade already had a counts-based
  distribution check (`check_distribution`, Hellinger fidelity) and a graph
  branch for a counts oracle, but no loader; `bench/run_single._load_oracle`
  now loads `{"counts": ...}` for the `distribution` kind. The checker was
  validated on the hand-computed case (accepts the right circuit, rejects the
  bit-reversed one at Hellinger 0.5625) before it accepts anything. The same
  validation found that the sampled check alone cannot tell a reversed register
  from the right one when the biases are close (a reversed (0.75, 0.8, 0.7)
  reads above 0.99). So acceptance also requires the exact output distribution to
  match within 1e-3, and a variation is used only if reversing its register
  changes the distribution by at least 0.05.
- **Leakage gate, phase 1.** Lexical (word 5-gram Jaccard, exact), structural
  (family id vs the suite's task-id families; one registration per key) and the
  post-generation circuit check against the references of the same width and
  kind. Registry is the only writer; generation takes ids; `export` re-runs the
  gate and refuses on any failure; the gate version is a hash of the test set's
  content. Semantic measure: phase 2, and each reject log says "not measured".
  **Calibration finding:** the first design's rule (reject anything as close as the
  LEAST similar twin pair) is unusable: that pair is at Jaccard 0.0076, and the 5th
  percentile of twins (0.051) is below the 95th percentile of cross-family
  test-vs-test pairs (0.122), so lexically twins and unrelated tasks overlap.
  Thresholds in use (`bench/leakage_calibration.json`): reject at the median twin
  (0.283), review from the cross-family 95th percentile (0.122). The lexical
  measure finds copies and light edits; what it cannot see (a perturbed rewrite,
  a shared mechanism) is what the semantic measure and the adjacency table are for.
  Result on the 80 pilot statements: all pass; the highest lexical score against
  any test task is 0.029.
