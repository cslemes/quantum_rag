"""US3 — verification without a reference (FR-009–FR-013). Deterministic
parser and evaluator for the assertion language designed in plan.md
§Verificação sem referência. NO import from `qcagent.llm` anywhere in this
module, ever — `tests/contract/test_architecture.py` enforces this the same
way it already does for the rest of `validators/` (Principio I): an LLM may
at most PROPOSE an assertion as a hypothesis (a future, separate concern,
not implemented here); it never gets a vote on whether one holds.

Every ket/Pauli string in this file shares ONE convention: leftmost
character = highest-indexed qubit, rightmost = qubit 0 — identical to
Qiskit's own `Statevector.probabilities_dict()`/`Pauli` label convention,
and verified (not assumed) to be exactly `int(ket_string, 2)` indexing into
`Statevector.data` before this file was written. `MEASURES`'s WITH-LIST form
is the one deliberate exception — see `_evaluate_measures`'s docstring for
why, and for why its convention had to be implemented against the raw
`probabilities(qargs=...)` array rather than `probabilities_dict(qargs=...)`
specifically: Qiskit's own qargs-dict key rendering puts the FIRST-listed
qarg at the RIGHTMOST string position (verified empirically — the opposite
of what this grammar promises the with-list form does), so using it
directly here would have silently implemented the wrong convention despite
looking superficially correct on a palindromic test case.
"""

import cmath
import math
import re
from typing import Literal, cast

from qiskit import QuantumCircuit
from qiskit.circuit.library import get_standard_gate_name_mapping
from qiskit.quantum_info import SparsePauliOp, Statevector

from qcagent.state import (
    AmplitudeAssertion,
    AmplitudeTerm,
    Assertion,
    AssertionOutcome,
    EigenstateAssertion,
    GateRestrictionAssertion,
    MeasuresAssertion,
)

# Re-exported: `NotEvaluable` is part of this module's public surface (every
# evaluator here can return it) but it now lives next to the
# measurement-stripping primitive it comes from, so the reference oracles in
# semantic.py share one implementation of the rule instead of re-deriving it.
# For assertions it has exactly two causes: a `phase_diff` whose referenced
# amplitude is ~0 (phase undefined there), and ANY state-based assertion
# against a circuit with a non-final measurement or reset. NEVER a
# parse-time concept (see `AssertionParseError`) — it can only be known once
# a real `Statevector` exists to check against.
from qcagent.validators.circuits import NotEvaluable, prepared_statevector, unitary_part

# Exact-simulation tolerance (no shot noise involved — every evaluation here
# is against a real Statevector, not a sampled measurement). Reuses the
# atol already established for D3b's `_check_by_composition`, not
# bench/validate_oracles.py's Monte-Carlo-calibrated constants, which exist
# for a different regime entirely (real sampled measurement, SANITY_
# FIDELITY_MIN=0.98/ENERGY_SANITY_TOL=0.02).
DEFAULT_TOL = 1e-9

# `~=` on MEASURES's implicit "certain" comparison uses a looser bound than
# DEFAULT_TOL on purpose: "deterministic" means "probability indistinguishable
# from 1 given floating-point roundoff across a real transpiled circuit", not
# "bit-identical to 1.0" — 1e-6 is still far tighter than any shot-noise
# regime and comfortably separates "certain" from "merely likely".
MEASURES_CERTAINTY_TOL = 1e-6

# get_standard_gate_name_mapping() covers Qiskit's fixed-arity "standard"
# gates (54 at the time this was written) but NOT the multi-controlled
# variable-arity family (mcx, mcphase, ...) or the barrier directive — all
# real, valid instruction names, just not "standard gates" in Qiskit's own
# sense. Extended with exactly the ones this project's own oracle-building
# code already uses (mcx — confirmed via `grep` before writing this, not
# guessed) plus its closest siblings, deliberately NOT an attempt at
# exhaustive coverage — extend this set if a real task needs another one.
KNOWN_GATE_NAMES = frozenset(get_standard_gate_name_mapping().keys()) | {
    "barrier",
    "mcx",
    "mcphase",
    "mcrx",
    "mcry",
    "mcrz",
}

# Instructions that are not "gates" for the purpose of a gate-set restriction
# — exactly Qiskit's own `BasisTranslator.basic_instrs`, the list Qiskit
# unions into EVERY target basis because no basis ever has to name them.
# Copied rather than invented, and pinned against the installed Qiskit source
# by test_assertions.py::test_non_gate_instructions_match_qiskits_own_list.
# Without this, `qc.measure_all()` (which adds `measure` AND a `barrier`)
# made `GATES_SUBSET_OF({"h", "cx"})` reject a correct H+CX circuit — found
# by the first end-to-end run over realistic generated code, not by any
# unit test, none of which used a measured circuit.
NON_GATE_INSTRUCTIONS = frozenset({"measure", "reset", "barrier", "snapshot", "delay", "store"})

_QUBIT_LABEL_TO_PAULI_EIGEN: dict[str, tuple[str, Literal[1, -1]]] = {
    "0": ("Z", 1),
    "1": ("Z", -1),
    "+": ("X", 1),
    "-": ("X", -1),
    "i": ("Y", 1),
    "-i": ("Y", -1),
}


class AssertionParseError(Exception):
    """Raised for any malformed assertion (FR-013) — refused explicitly,
    never silently ignored. The caller (planner's `rejected_input` path,
    T090) turns this into an explicit refusal before any generation
    happens, reusing the mechanism T024b already established rather than
    creating a second one."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_INPUT_RE = re.compile(r"^INPUT\(\|([01]+)>\)\s+THEN\s+(.*)$")
_TERM_RE = re.compile(r"^(PROBABILITY|AMPLITUDE)\(\|([01]+)>\)")
_PHASE_DIFF_TERM_RE = re.compile(r"^PHASE_DIFF\(\|([01]+)>\s*,\s*\|([01]+)>\)")
_CMP_RE = re.compile(r"^\s*(==|~=|>=|<=)\s*")
_NUMBER_RE = re.compile(r"^(-?pi|-?\d+(?:\.\d+)?)$")
_MEASURES_BARE_RE = re.compile(r'^MEASURES\s*==\s*"([01]+)"$')
_MEASURES_LIST_RE = re.compile(r'^MEASURES\(\s*\[([^\]]*)\]\s*\)\s*==\s*"([01]+)"$')
_EIGENSTATE_RE = re.compile(r'^EIGENSTATE_OF\("([IXYZ]+)"\s*,\s*([+-]?1)\)$')
_QUBIT_RE = re.compile(r'^QUBIT\((\d+)\)\s*==\s*"\|(0|1|\+|-i|-|i)>"$')
_GATES_RE = re.compile(r"^GATES_SUBSET_OF\(\{([^}]*)\}\)$")


def _parse_number(s: str) -> float:
    m = _NUMBER_RE.match(s.strip())
    if m is None:
        raise AssertionParseError(f"expected a number (or pi/-pi), got {s!r}")
    tok = m.group(1)
    if tok in ("pi", "-pi"):
        return math.pi if tok == "pi" else -math.pi
    return float(tok)


def _require_length(s: str, n_qubits: int, what: str) -> None:
    if len(s) != n_qubits:
        raise AssertionParseError(
            f"{what} has length {len(s)}, but the circuit has {n_qubits} qubits — "
            f"no implicit padding in this grammar, write all {n_qubits} characters"
        )


def _parse_term(s: str, n_qubits: int) -> tuple[AmplitudeTerm, str]:
    """Parses a leading PROBABILITY(...)/AMPLITUDE(...)/PHASE_DIFF(...) term
    off the front of `s`. Returns (term, remainder)."""
    m = _PHASE_DIFF_TERM_RE.match(s)
    if m is not None:
        a, b = m.group(1), m.group(2)
        _require_length(a, n_qubits, "PHASE_DIFF's first ket")
        _require_length(b, n_qubits, "PHASE_DIFF's second ket")
        return AmplitudeTerm(kind="phase_diff", basis_state=a, basis_state_b=b), s[m.end() :]

    m = _TERM_RE.match(s)
    if m is not None:
        kind: Literal["probability", "amplitude"] = (
            "probability" if m.group(1) == "PROBABILITY" else "amplitude"
        )
        ket = m.group(2)
        _require_length(ket, n_qubits, f"{m.group(1)}'s ket")
        return AmplitudeTerm(kind=kind, basis_state=ket), s[m.end() :]

    raise AssertionParseError(
        f"expected PROBABILITY(...), AMPLITUDE(...), or PHASE_DIFF(...,...) at {s!r}"
    )


def _parse_amplitude_assertion(
    s: str, n_qubits: int, input_state: str | None
) -> AmplitudeAssertion:
    lhs, rest = _parse_term(s, n_qubits)
    cmp_m = _CMP_RE.match(rest)
    if cmp_m is None:
        raise AssertionParseError(f"expected a comparator (==, ~=, >=, <=) after {s!r}")
    # _CMP_RE's alternation is exactly this Literal's members, so the cast
    # is a type-checker formality, not an unchecked assumption.
    comparator = cast(Literal["==", "~=", ">=", "<="], cmp_m.group(1))
    rest = rest[cmp_m.end() :]

    # Only a genuine "this isn't a term at all" failure falls through to the
    # numeric-rhs path below. A term that parses but violates a grammar rule
    # (PHASE_DIFF on the rhs, a kind mismatch, trailing text) must raise
    # directly — an earlier version of this function caught
    # AssertionParseError around all three checks too, which swallowed each
    # one's specific message and reported a misleading "expected a number,
    # got ''" instead. Confirmed broken and fixed before this file's tests
    # were written, not after.
    rhs_term: AmplitudeTerm | None
    try:
        rhs_term, rest_after_term = _parse_term(rest, n_qubits)
    except AssertionParseError:
        rhs_term, rest_after_term = None, rest

    rhs: AmplitudeTerm | float
    if rhs_term is not None:
        if rhs_term.kind == "phase_diff":
            raise AssertionParseError(
                "PHASE_DIFF may only appear on the left-hand side, compared against a "
                "numeric angle — comparing two PHASE_DIFF terms is not supported"
            )
        if rhs_term.kind != lhs.kind:
            raise AssertionParseError(
                f"type mismatch: comparing {lhs.kind.upper()} to {rhs_term.kind.upper()} — "
                "both sides of an amplitude assertion must be the same kind"
            )
        if rest_after_term.strip():
            raise AssertionParseError(f"unexpected trailing text: {rest_after_term!r}")
        rhs = rhs_term
    else:
        rhs = _parse_number(rest_after_term)

    return AmplitudeAssertion(lhs=lhs, comparator=comparator, rhs=rhs, input_state=input_state)


def _parse_measures(s: str, n_qubits: int, input_state: str | None) -> MeasuresAssertion:
    m = _MEASURES_BARE_RE.match(s)
    if m is not None:
        expected = m.group(1)
        _require_length(expected, n_qubits, "MEASURES's expected bitstring (bare form)")
        return MeasuresAssertion(qubits=None, expected=expected, input_state=input_state)

    m = _MEASURES_LIST_RE.match(s)
    if m is not None:
        raw_qubits, expected = m.group(1), m.group(2)
        try:
            qubits = [int(tok.strip()) for tok in raw_qubits.split(",") if tok.strip()]
        except ValueError as exc:
            raise AssertionParseError(
                f"MEASURES qubit list is not a list of integers: {raw_qubits!r}"
            ) from exc
        if not qubits:
            raise AssertionParseError(
                "MEASURES(...) qubit list is empty — use the bare form for all qubits"
            )
        if len(qubits) != len(set(qubits)):
            raise AssertionParseError(f"MEASURES qubit list has duplicate indices: {qubits}")
        for q in qubits:
            if not (0 <= q < n_qubits):
                raise AssertionParseError(
                    f"MEASURES qubit index {q} out of range for {n_qubits} qubits"
                )
        if len(expected) != len(qubits):
            raise AssertionParseError(
                f"MEASURES bitstring has length {len(expected)}, "
                f"but {len(qubits)} qubits were listed"
            )
        return MeasuresAssertion(qubits=qubits, expected=expected, input_state=input_state)

    raise AssertionParseError(f'expected MEASURES == "..." or MEASURES([...]) == "...", got {s!r}')


def _parse_eigenstate(s: str, n_qubits: int, input_state: str | None) -> EigenstateAssertion:
    m = _EIGENSTATE_RE.match(s)
    if m is None:
        raise AssertionParseError(f'expected EIGENSTATE_OF("<pauli>", +1|-1), got {s!r}')
    pauli, eig = m.group(1), m.group(2)
    _require_length(pauli, n_qubits, "EIGENSTATE_OF's Pauli string")
    eigenvalue: Literal[1, -1] = -1 if eig == "-1" else 1
    return EigenstateAssertion(pauli_string=pauli, eigenvalue=eigenvalue, input_state=input_state)


def _parse_qubit_sugar(s: str, n_qubits: int, input_state: str | None) -> EigenstateAssertion:
    """`QUBIT(q) == "|label>"` desugars directly to `EigenstateAssertion` —
    never a separate runtime kind (plan.md: "EIGENSTATE_OF retained for the
    general case, QUBIT is shorthand" — this is where that's literal)."""
    m = _QUBIT_RE.match(s)
    if m is None:
        raise AssertionParseError(f'expected QUBIT(<index>) == "|0>|1>|+>|->|i>|-i>", got {s!r}')
    q, label = int(m.group(1)), m.group(2)
    if not (0 <= q < n_qubits):
        raise AssertionParseError(f"QUBIT index {q} out of range for {n_qubits} qubits")
    pauli_char, eigenvalue = _QUBIT_LABEL_TO_PAULI_EIGEN[label]
    # position q -> leftmost-is-qubit-(n-1) convention: same index math as
    # everywhere else in this file, not a new rule.
    pauli_string = "".join(pauli_char if (n_qubits - 1 - i) == q else "I" for i in range(n_qubits))
    return EigenstateAssertion(
        pauli_string=pauli_string, eigenvalue=eigenvalue, input_state=input_state
    )


def _parse_gate_restriction(s: str, input_state: str | None) -> GateRestrictionAssertion:
    if input_state is not None:
        raise AssertionParseError(
            "GATES_SUBSET_OF is purely structural (over the circuit's gate list, not its "
            "output state) — an INPUT(...) prefix on it doesn't mean anything, and is refused "
            "rather than silently ignored"
        )
    m = _GATES_RE.match(s)
    if m is None:
        raise AssertionParseError(f'expected GATES_SUBSET_OF({{"g1", "g2", ...}}), got {s!r}')
    raw = m.group(1)
    names = [tok.strip().strip('"').strip("'") for tok in raw.split(",") if tok.strip()]
    if not names:
        raise AssertionParseError(
            "GATES_SUBSET_OF({}) is empty — no circuit with any gate could pass"
        )
    unknown = [n for n in names if n not in KNOWN_GATE_NAMES]
    if unknown:
        raise AssertionParseError(
            f"unknown gate name(s) {unknown!r} — not in Qiskit's own instruction-name "
            f"vocabulary. Refused explicitly rather than accepted: an unrecognized name left "
            f"in the set would make the assertion's error message (if it ever fails) "
            f"misleading about which gate was actually the problem."
        )
    return GateRestrictionAssertion(allowed_gates=frozenset(names))


def parse_one(line: str, n_qubits: int) -> Assertion:
    """Parses a single assertion line. Raises `AssertionParseError` — never
    returns a partially-understood result — for anything that doesn't match
    the grammar exactly (FR-013)."""
    text = line.strip()
    if not text:
        raise AssertionParseError("empty assertion")

    input_state: str | None = None
    input_m = _INPUT_RE.match(text)
    if input_m is not None:
        input_state = input_m.group(1)
        _require_length(input_state, n_qubits, "INPUT(...)'s ket")
        text = input_m.group(2).strip()

    if text.startswith("GATES_SUBSET_OF("):
        return _parse_gate_restriction(text, input_state)
    if text.startswith("QUBIT("):
        return _parse_qubit_sugar(text, n_qubits, input_state)
    if text.startswith("EIGENSTATE_OF("):
        return _parse_eigenstate(text, n_qubits, input_state)
    if text.startswith("MEASURES"):
        return _parse_measures(text, n_qubits, input_state)
    if text.startswith(("PROBABILITY(", "AMPLITUDE(", "PHASE_DIFF(")):
        return _parse_amplitude_assertion(text, n_qubits, input_state)

    raise AssertionParseError(
        f"unrecognized assertion form: {text!r} — expected one of PROBABILITY/AMPLITUDE/"
        f"PHASE_DIFF/MEASURES/EIGENSTATE_OF/QUBIT/GATES_SUBSET_OF"
    )


def parse_assertions(text: str, n_qubits: int) -> list[Assertion]:
    """Parses one assertion per non-empty, non-comment (`#`) line. Raises
    `AssertionParseError` on the FIRST malformed line — no partial results,
    matching FR-013's "refused explicitly, never silently ignored": a batch
    with one bad line is entirely refused, not silently trimmed down to the
    lines that happened to parse."""
    assertions: list[Assertion] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            assertions.append(parse_one(line, n_qubits))
        except AssertionParseError as exc:
            raise AssertionParseError(f"line {lineno}: {exc}") from exc
    return assertions


# ---------------------------------------------------------------------------
# Register width — stated by the user's own assertions
# ---------------------------------------------------------------------------

_KET_RE = re.compile(r"\|([01]+)>")


def _assertion_lines(text: str) -> list[str]:
    """Non-empty assertion lines with `#` comments removed — the same line
    split `parse_assertions` uses, so the width readers see what it sees."""
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def width_statements(text: str) -> list[tuple[str, set[int]]]:
    """One `(assertion_line, widths)` entry per assertion that STATES a
    register width, read off its full-register strings: kets in
    PROBABILITY/AMPLITUDE/PHASE_DIFF, the bare MEASURES bitstring,
    EIGENSTATE_OF's Pauli string, and INPUT's ket. Counted per ASSERTION,
    not per string — `AMPLITUDE(|00>) == AMPLITUDE(|11>)` is one statement.

    This is what lets the user's direct statement, not the planner's
    extraction, define the register (planner.py::check_assertions), and how
    many assertions back that width is part of the evidence: one assertion
    disagreeing with the planner is ambiguity to ask about, two or more
    agreeing is strong enough to correct the planner.

    Forms that carry only qubit INDICES (QUBIT, MEASURES([...])) and
    GATES_SUBSET_OF state no width and produce no entry; see
    `minimum_register_width`. A line this reader can't classify produces no
    entry either — the parser, run afterwards with the resulting width, is
    still the one that refuses it.
    """
    statements: list[tuple[str, set[int]]] = []
    for line in _assertion_lines(text):
        widths: set[int] = set()
        body = line
        input_m = _INPUT_RE.match(line)
        if input_m is not None:
            widths.add(len(input_m.group(1)))
            body = input_m.group(2).strip()
        if body.startswith(("PROBABILITY(", "AMPLITUDE(", "PHASE_DIFF(")):
            widths.update(len(ket) for ket in _KET_RE.findall(body))
        elif (bare := _MEASURES_BARE_RE.match(body)) is not None:
            widths.add(len(bare.group(1)))
        elif (eig := _EIGENSTATE_RE.match(body)) is not None:
            widths.add(len(eig.group(1)))
        if widths:
            statements.append((line, widths))
    return statements


def declared_register_widths(text: str) -> set[int]:
    """Every register width the user's assertions state (see
    `width_statements`). More than one means the assertions disagree among
    themselves, which IS a user error."""
    return {w for _, widths in width_statements(text) for w in widths}


def minimum_register_width(text: str) -> int:
    """The smallest register the index-only forms need (highest qubit index
    named by QUBIT or MEASURES([...]), plus one); 0 if none name an index.
    A lower bound, not a width — see `declared_register_widths`."""
    lowest = 0
    for line in _assertion_lines(text):
        input_m = _INPUT_RE.match(line)
        if input_m is not None:
            line = input_m.group(2).strip()
        if (qubit := _QUBIT_RE.match(line)) is not None:
            lowest = max(lowest, int(qubit.group(1)) + 1)
        elif (listed := _MEASURES_LIST_RE.match(line)) is not None:
            try:
                indices = [int(t) for t in listed.group(1).split(",") if t.strip()]
            except ValueError:
                continue
            if indices:
                lowest = max(lowest, max(indices) + 1)
    return lowest


def register_width(assertion: Assertion) -> int | None:
    """The register width a PARSED assertion is written for, or None for the
    forms that don't fix one (MEASURES([...]) and GATES_SUBSET_OF)."""
    if isinstance(assertion, AmplitudeAssertion):
        return len(assertion.lhs.basis_state)
    if isinstance(assertion, MeasuresAssertion):
        return len(assertion.expected) if assertion.qubits is None else None
    if isinstance(assertion, EigenstateAssertion):
        return len(assertion.pauli_string)
    return None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _prepared_statevector(
    circuit: QuantumCircuit, input_state: str | None
) -> Statevector | NotEvaluable:
    """Evolves `circuit` from |0...0> (input_state=None) or from the
    computational basis state `input_state` names (INPUT(...) — X on every
    '1' bit position, in this file's one shared ket convention).

    Final measurements are stripped first: an assertion is about the state
    the circuit PREPARES, and `measure_all()` at the end — which real
    generated code does constantly — doesn't change that state, it samples
    it. Before this, `Statevector.from_instruction` raised on any measured
    circuit and took the whole graph down (found end to end, T092). A
    measurement or reset that is NOT final (mid-circuit) genuinely leaves
    no pure output state to assert about, so that case is "not evaluable",
    never a crash and never a forced verdict.
    """
    if input_state is None:
        return prepared_statevector(circuit)
    n = circuit.num_qubits
    prep = QuantumCircuit(n)
    for i, bit in enumerate(input_state):
        if bit == "1":
            # leftmost char (i=0) is qubit n-1, rightmost is qubit 0.
            prep.x(n - 1 - i)
    return prepared_statevector(prep.compose(unitary_part(circuit)))


def _evaluate_term(term: AmplitudeTerm, sv: Statevector) -> float | NotEvaluable:
    if term.kind == "probability":
        return float(abs(sv.data[int(term.basis_state, 2)]) ** 2)
    if term.kind == "amplitude":
        return float(abs(sv.data[int(term.basis_state, 2)]))
    # phase_diff
    assert term.basis_state_b is not None
    amp_a = sv.data[int(term.basis_state, 2)]
    amp_b = sv.data[int(term.basis_state_b, 2)]

    if abs(amp_a) < 1e-9:
        return NotEvaluable(f"amplitude of |{term.basis_state}> is ~0 — phase is undefined there")
    if abs(amp_b) < 1e-9:
        return NotEvaluable(f"amplitude of |{term.basis_state_b}> is ~0 — phase is undefined there")
    diff = cmath.phase(amp_b) - cmath.phase(amp_a)
    # normalize to (-pi, pi]
    while diff <= -math.pi:
        diff += 2 * math.pi
    while diff > math.pi:
        diff -= 2 * math.pi
    return diff


def _compare(value: float, comparator: str, target: float) -> bool:
    if comparator == "==":
        return value == target
    if comparator == "~=":
        return abs(value - target) <= DEFAULT_TOL
    if comparator == ">=":
        return value >= target - DEFAULT_TOL
    if comparator == "<=":
        return value <= target + DEFAULT_TOL
    raise AssertionError(f"unreachable comparator {comparator!r}")  # parser already validated this


def _evaluate_amplitude(assertion: AmplitudeAssertion, circuit: QuantumCircuit) -> AssertionOutcome:
    sv = _prepared_statevector(circuit, assertion.input_state)
    if isinstance(sv, NotEvaluable):
        return AssertionOutcome(assertion=assertion, passed=None, detail=sv.reason)
    lhs_val = _evaluate_term(assertion.lhs, sv)
    if isinstance(lhs_val, NotEvaluable):
        return AssertionOutcome(assertion=assertion, passed=None, detail=lhs_val.reason)

    if isinstance(assertion.rhs, AmplitudeTerm):
        rhs_val = _evaluate_term(assertion.rhs, sv)
        if isinstance(rhs_val, NotEvaluable):
            return AssertionOutcome(assertion=assertion, passed=None, detail=rhs_val.reason)
    else:
        rhs_val = assertion.rhs

    ok = _compare(lhs_val, assertion.comparator, rhs_val)
    detail = f"lhs={lhs_val:.6g} {assertion.comparator} rhs={rhs_val:.6g}"
    return AssertionOutcome(assertion=assertion, passed=ok, detail=detail)


def _evaluate_measures(assertion: MeasuresAssertion, circuit: QuantumCircuit) -> AssertionOutcome:
    """WITH-LIST form deliberately does NOT use `Statevector.
    probabilities_dict(qargs=...)`'s own string keys — verified empirically
    (before this function was written) that Qiskit puts the FIRST-listed
    qarg at the RIGHTMOST bit of that rendered string, the opposite of what
    this grammar promises (`qubits[i]` <-> `expected[i]`, both read
    left-to-right). Built from the raw `probabilities(qargs=...)` array
    instead, indexed by a formula whose correctness was checked against a
    real oracle (`bv_4q`) and against a second, deliberately asymmetric
    hand-built circuit before being trusted here — an earlier attempt using
    the dict-key form passed the first (palindromic-secret) check by
    coincidence and only failed on the second, asymmetric one.
    """
    sv = _prepared_statevector(circuit, assertion.input_state)
    if isinstance(sv, NotEvaluable):
        return AssertionOutcome(assertion=assertion, passed=None, detail=sv.reason)

    if assertion.qubits is None:
        prob = abs(sv.data[int(assertion.expected, 2)]) ** 2
    else:
        probs = sv.probabilities(qargs=assertion.qubits)
        j = sum(int(bit) << i for i, bit in enumerate(assertion.expected))
        prob = probs[j]

    ok = bool(prob >= 1.0 - MEASURES_CERTAINTY_TOL)
    threshold = 1.0 - MEASURES_CERTAINTY_TOL
    detail = f"probability of {assertion.expected!r} = {prob:.6g} (need >= {threshold:.6g})"
    return AssertionOutcome(assertion=assertion, passed=ok, detail=detail)


def _evaluate_eigenstate(
    assertion: EigenstateAssertion, circuit: QuantumCircuit
) -> AssertionOutcome:
    """Checks the RESIDUAL NORM ||H|psi> - eigenvalue|psi>||, never
    `<psi|H|psi> == eigenvalue` alone — a correct expectation value does not
    imply the state actually IS an eigenstate (F2, report-notes.md: a
    measurement-based check can be structurally blind, not just loose,
    applied here preventively). `tests/unit/test_assertions.py` proves this
    with an adversarial state that has the right expectation value but is
    NOT a true eigenstate, and confirms it correctly fails."""
    sv = _prepared_statevector(circuit, assertion.input_state)
    if isinstance(sv, NotEvaluable):
        return AssertionOutcome(assertion=assertion, passed=None, detail=sv.reason)
    op = SparsePauliOp(assertion.pauli_string)
    psi = sv.data
    h_psi = op.to_matrix() @ psi
    residual = h_psi - assertion.eigenvalue * psi
    residual_norm = float((residual.conj() @ residual).real ** 0.5)
    ok = bool(residual_norm <= 1e-6)
    detail = f"||H|psi> - ({assertion.eigenvalue})|psi>|| = {residual_norm:.6g} (need <= 1e-6)"
    return AssertionOutcome(assertion=assertion, passed=ok, detail=detail)


def _evaluate_gate_restriction(
    assertion: GateRestrictionAssertion, circuit: QuantumCircuit
) -> AssertionOutcome:
    used = {instr.operation.name for instr in circuit.data} - NON_GATE_INSTRUCTIONS
    extra = used - assertion.allowed_gates
    ok = not extra
    detail = (
        "all gates within the allowed set" if ok else f"disallowed gate(s) used: {sorted(extra)}"
    )
    return AssertionOutcome(assertion=assertion, passed=ok, detail=detail)


def _width_mismatch(assertion: Assertion, circuit: QuantumCircuit) -> str | None:
    """A circuit whose width differs from the one the user's assertion is
    written for contradicts the user's own statement, so it is a VIOLATION
    (`passed=False`, named, back into the repair loop) — not "not evaluable",
    and never evaluated anyway. Evaluating anyway was worse than crashing:
    `PROBABILITY(|11>)` against a 3-qubit circuit read index 3 = |011>, a
    different basis state, and PASSED; EIGENSTATE_OF/QUBIT raised a matrix
    dimension error that took the graph down. Found when the user's
    assertions became the source of truth for the register width."""
    n = circuit.num_qubits
    width = register_width(assertion)
    if width is not None and width != n:
        return f"assertion is written for {width} qubits but the circuit has {n}"
    if isinstance(assertion, MeasuresAssertion) and assertion.qubits is not None:
        highest = max(assertion.qubits)
        if highest >= n:
            return f"assertion measures qubit {highest} but the circuit has only {n} qubits"
    return None


def evaluate_assertions(
    assertions: list[Assertion], circuit: QuantumCircuit
) -> list[AssertionOutcome]:
    """Evaluates every assertion independently (FR-011) — one
    `AssertionOutcome` per input assertion, same order, regardless of
    whether earlier ones failed."""
    outcomes: list[AssertionOutcome] = []
    for a in assertions:
        mismatch = _width_mismatch(a, circuit)
        if mismatch is not None:
            outcomes.append(AssertionOutcome(assertion=a, passed=False, detail=mismatch))
            continue
        if isinstance(a, AmplitudeAssertion):
            outcomes.append(_evaluate_amplitude(a, circuit))
        elif isinstance(a, MeasuresAssertion):
            outcomes.append(_evaluate_measures(a, circuit))
        elif isinstance(a, EigenstateAssertion):
            outcomes.append(_evaluate_eigenstate(a, circuit))
        elif isinstance(a, GateRestrictionAssertion):
            outcomes.append(_evaluate_gate_restriction(a, circuit))
        else:  # pragma: no cover - exhaustive over the Assertion union
            raise AssertionError(f"unreachable assertion kind {a!r}")
    return outcomes


# ---------------------------------------------------------------------------
# Rendering — the inverse of the parser
# ---------------------------------------------------------------------------


def _render_term(term: AmplitudeTerm) -> str:
    if term.kind == "phase_diff":
        return f"PHASE_DIFF(|{term.basis_state}>,|{term.basis_state_b}>)"
    return f"{term.kind.upper()}(|{term.basis_state}>)"


def render_assertion(assertion: Assertion) -> str:
    """The assertion back in the grammar the user wrote it in. Lives next to
    the parser because it IS the parser's inverse, and is public because
    three places must name an assertion identically: the guarantee report,
    the critic's hint prompt, and the `ErrorRecord` that reaches the
    generator. FR-012 requires the violated assertion be NAMED in the repair
    loop; before this was shared, the generator only ever saw the numeric
    detail ("lhs=0 ~= rhs=0.5") and the critic only the kind ("amplitude"),
    neither of which says WHICH of two probability assertions failed.
    Found end to end (T092) by reading the prompts the model received."""
    if isinstance(assertion, AmplitudeAssertion):
        lhs = _render_term(assertion.lhs)
        rhs = (
            _render_term(assertion.rhs)
            if isinstance(assertion.rhs, AmplitudeTerm)
            else f"{assertion.rhs:g}"
        )
        text = f"{lhs} {assertion.comparator} {rhs}"
    elif isinstance(assertion, MeasuresAssertion):
        target = f'== "{assertion.expected}"'
        if assertion.qubits is None:
            text = f"MEASURES {target}"
        else:
            text = f"MEASURES({assertion.qubits}) {target}"
    elif isinstance(assertion, EigenstateAssertion):
        text = f'EIGENSTATE_OF("{assertion.pauli_string}", {assertion.eigenvalue:+d})'
    elif isinstance(assertion, GateRestrictionAssertion):
        gates = ", ".join(f'"{g}"' for g in sorted(assertion.allowed_gates))
        text = f"GATES_SUBSET_OF({{{gates}}})"
    else:  # pragma: no cover - exhaustive over the Assertion union
        raise AssertionError(f"unreachable assertion kind {assertion!r}")

    input_state = getattr(assertion, "input_state", None)
    return f"INPUT(|{input_state}>) THEN {text}" if input_state is not None else text
