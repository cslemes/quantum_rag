"""What the circuit actually does, as a distribution over outcomes (FR-018).

DESCRIPTIVE, never evaluative. This module says what the circuit produces; it
says nothing about whether that is what was asked for. That distinction is
FR-017 in a new place: a reader who sees 50/50 on |000> and |111> will infer
correctness themselves, and the system must not appear to be making that
claim — so nothing here returns a verdict, a pass/fail, or a comparison.

Two sources, and which one is used is reported rather than assumed:

* EXACT — probabilities read off the statevector, with final measurements
  stripped. This is the default wherever a pure output state exists.
* SAMPLED — shots through Aer, used only where exact is impossible (a
  mid-circuit measurement or reset leaves no pure state).

Exact is preferred over sampling even for circuits that end in `measure_all()`,
and the reason is not aesthetic. The assertion grammar's `~=` tolerance is
`DEFAULT_TOL` (1e-9). A draft assertion built from an 8192-shot estimate would
read `PROBABILITY(|000>) ~= 0.4998` and then FAIL when checked — the interface
would be handing users broken assertions. A final measurement does not change
the state it samples, so the exact distribution is the same quantity the shots
estimate, without sampling noise the system does not actually have.
"""

from dataclasses import dataclass

from qiskit import QuantumCircuit

from qcagent.validators.assertions import DEFAULT_TOL
from qcagent.validators.circuits import NotEvaluable, no_pure_state_reason, prepared_statevector
from qcagent.validators.simulator import make_simulator

# Enough outcomes to show structure, few enough to read. 2^n is unreadable
# past a handful of qubits and the tail is almost always noise-floor terms.
DEFAULT_TOP_K = 8

# Outcomes below this are omitted entirely rather than listed as ~0. Floating
# point leaves 1e-33-type residue on exactly-zero amplitudes, and rendering
# those as outcomes implies the circuit can produce them.
NEGLIGIBLE = 1e-9

SHOTS = 8192


@dataclass(frozen=True)
class Outcome:
    """One basis state and how often the circuit produces it.

    `bitstring` uses this project's ONE ket convention — leftmost character is
    the highest-indexed qubit — so it can be pasted into an assertion without
    being reinterpreted. That is the whole point of the affordance built on
    this: the string shown IS the string the grammar expects.
    """

    bitstring: str
    probability: float


@dataclass(frozen=True)
class Distribution:
    """What the circuit does. No verdict, by construction."""

    outcomes: list[Outcome]  # descending probability, at most top_k
    source: str  # "exact" | "sampled"
    n_qubits: int
    shown: int  # how many outcomes are listed
    total_outcomes: int  # how many have non-negligible probability
    omitted_probability: float  # mass in the outcomes NOT shown

    @property
    def truncated(self) -> bool:
        return self.total_outcomes > self.shown


def outcome_distribution(
    circuit: QuantumCircuit, *, top_k: int = DEFAULT_TOP_K, seed: int = 1
) -> Distribution | NotEvaluable:
    """The circuit's output distribution, or why it has none.

    Returns `NotEvaluable` for the same cases the assertion evaluator does —
    unbound parameters, and non-final measurement or reset — rather than
    inventing a distribution for a circuit that does not define one.
    """
    statevector = prepared_statevector(circuit)
    if isinstance(statevector, NotEvaluable):
        return _sampled(circuit, top_k=top_k, seed=seed)

    probabilities = statevector.probabilities()
    n_qubits = circuit.num_qubits
    pairs = [
        (format(index, f"0{n_qubits}b"), float(value))
        for index, value in enumerate(probabilities)
        if value > NEGLIGIBLE
    ]
    return _assemble(pairs, source="exact", n_qubits=n_qubits, top_k=top_k)


def _sampled(circuit: QuantumCircuit, *, top_k: int, seed: int) -> Distribution | NotEvaluable:
    """Shots, for circuits with no pure output state to read exactly.

    A circuit with a mid-circuit measurement still HAS a distribution even
    though it has no statevector, which is precisely why this fallback exists
    rather than reporting nothing.
    """
    if "measure" not in circuit.count_ops():
        # No pure state AND no measurement: unbound parameters, most likely.
        # Nothing to sample and nothing to compute.
        return NotEvaluable(no_pure_state_reason(circuit) or "no output distribution")
    try:
        simulator = make_simulator(circuit.num_qubits, seed)
        counts = simulator.run(circuit, shots=SHOTS, seed_simulator=seed).result().get_counts()
    except Exception as exc:  # noqa: BLE001 — reported, never a crash
        return NotEvaluable(f"simulation failed: {type(exc).__name__}: {exc}")

    total = sum(counts.values()) or 1
    # Qiskit's count keys carry spaces between classical registers; the ket
    # convention this project uses has no separators.
    pairs = [(bits.replace(" ", ""), n / total) for bits, n in counts.items()]
    return _assemble(pairs, source="sampled", n_qubits=circuit.num_qubits, top_k=top_k)


def _assemble(
    pairs: list[tuple[str, float]], *, source: str, n_qubits: int, top_k: int
) -> Distribution:
    # Sorted by probability, then bitstring: ties must not depend on dict
    # ordering, for the same reason the retrieval ordering is total (F17).
    ordered = sorted(pairs, key=lambda pair: (-pair[1], pair[0]))
    shown = ordered[:top_k]
    return Distribution(
        outcomes=[Outcome(bits, probability) for bits, probability in shown],
        source=source,
        n_qubits=n_qubits,
        shown=len(shown),
        total_outcomes=len(ordered),
        omitted_probability=sum(probability for _, probability in ordered[top_k:]),
    )


def draft_assertion(outcome: Outcome, *, n_qubits: int) -> str:
    """An assertion the user could declare, built from an observed outcome.

    This is the on-ramp to US3: seeing the distribution is how someone
    discovers what to assert, and the hardest part of writing the first
    assertion is the first token, not the fifth.

    The drafted text MUST parse and MUST hold against the circuit it came
    from, or the affordance hands out broken assertions — which is worse than
    no affordance. Two consequences:

    * the probability is emitted at full precision, not rounded to something
      prettier, because `~=` compares within 1e-9;
    * a near-certain outcome drafts as `MEASURES`, which is the form that
      reads best aloud and carries its own looser certainty tolerance.
    """
    if outcome.probability > 1 - 1e-6:
        return f'MEASURES == "{outcome.bitstring}"'
    return f"PROBABILITY(|{outcome.bitstring}>) ~= {_readable(outcome.probability)}"


def _readable(probability: float) -> str:
    """The coarsest rounding that STILL holds within the grammar's tolerance.

    A Bell amplitude comes back as 0.4999999999999999, and drafting that is
    correct but unreadable; `0.5` is within 1.1e-16 and reads like something a
    person would write. One third rounds no coarser than 0.3333333333, because
    0.3333 is 3.3e-5 away and `~=` compares within 1e-9.

    The rounding is CHECKED against the tolerance rather than assumed to be
    safe — a prettier number that fails the assertion it was drafted for would
    be the worst possible outcome for this affordance.
    """
    for places in (1, 2, 3, 4, 6, 10):
        candidate = round(probability, places)
        if abs(candidate - probability) <= DEFAULT_TOL:
            return repr(candidate)
    return repr(probability)
