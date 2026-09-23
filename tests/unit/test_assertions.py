"""Tests for US3's assertion language (FR-009-013) — the parser and
evaluator in `validators/assertions.py`. See plan.md §Verificação sem
referência for the grammar and report-notes.md for the QUBO limitation this
grammar deliberately does not try to cover.
"""

import math
from pathlib import Path

import pytest
from qiskit import QuantumCircuit, qpy
from qiskit.quantum_info import Statevector

from qcagent.validators.assertions import (
    AssertionParseError,
    evaluate_assertions,
    parse_assertions,
    parse_one,
)

ORACLES = Path(__file__).parents[2] / "bench" / "oracles"


def _one(text: str, n_qubits: int, circuit: QuantumCircuit):
    assertions = parse_assertions(text, n_qubits)
    assert len(assertions) == 1
    return evaluate_assertions(assertions, circuit)[0]


def _bell_phi_plus() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    return qc


def _bell_phi_minus() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.z(0)
    qc.cx(0, 1)
    return qc


def _half_adder() -> QuantumCircuit:
    with open(ORACLES / "reversible_half_adder_4q.qpy", "rb") as f:
        return qpy.load(f)[0]


# ---------------------------------------------------------------------------
# PROBABILITY / AMPLITUDE — true and false cases
# ---------------------------------------------------------------------------


def test_probability_true_case() -> None:
    outcome = _one("PROBABILITY(|11>) ~= 0.5", 2, _bell_phi_plus())
    assert outcome.passed is True


def test_probability_false_case() -> None:
    outcome = _one("PROBABILITY(|01>) ~= 0.5", 2, _bell_phi_plus())
    assert outcome.passed is False


def test_amplitude_pairwise_comparison_true() -> None:
    outcome = _one("AMPLITUDE(|00>) == AMPLITUDE(|11>)", 2, _bell_phi_plus())
    assert outcome.passed is True


def test_amplitude_pairwise_comparison_false() -> None:
    outcome = _one("AMPLITUDE(|00>) == AMPLITUDE(|01>)", 2, _bell_phi_plus())
    assert outcome.passed is False


def test_probability_ge_le_comparators() -> None:
    assert _one("PROBABILITY(|11>) >= 0.4", 2, _bell_phi_plus()).passed is True
    assert _one("PROBABILITY(|11>) <= 0.4", 2, _bell_phi_plus()).passed is False


# ---------------------------------------------------------------------------
# PHASE_DIFF — Φ+ vs Φ-, and the NOT_EVALUABLE tri-state outcome
# ---------------------------------------------------------------------------


def test_phase_diff_distinguishes_phi_plus_from_phi_minus() -> None:
    """Φ+ and Φ- are indistinguishable by PROBABILITY alone (both give
    50/50 on |00>/|11>) — PHASE_DIFF is the only way this grammar tells
    them apart, which is the entire reason it exists."""
    plus = _one("PHASE_DIFF(|00>,|11>) ~= 0", 2, _bell_phi_plus())
    minus = _one("PHASE_DIFF(|00>,|11>) ~= 0", 2, _bell_phi_minus())

    assert plus.passed is True
    assert minus.passed is False


def test_phase_diff_not_evaluable_when_an_amplitude_is_zero() -> None:
    """Tri-state outcome: `passed=None`, never a false pass or fail, when
    the referenced amplitude is ~0 and the phase is genuinely undefined."""
    only_00 = QuantumCircuit(2)  # stays |00>, amplitude of |11> is exactly 0

    outcome = _one("PHASE_DIFF(|00>,|11>) ~= 0", 2, only_00)

    assert outcome.passed is None
    assert "amplitude" in outcome.detail
    assert "|11>" in outcome.detail


def test_phase_diff_on_rhs_is_rejected() -> None:
    with pytest.raises(AssertionParseError, match="PHASE_DIFF may only appear"):
        parse_one("PHASE_DIFF(|00>,|11>) == PHASE_DIFF(|01>,|10>)", 2)


def test_amplitude_kind_mismatch_is_rejected() -> None:
    with pytest.raises(AssertionParseError, match="type mismatch"):
        parse_one("AMPLITUDE(|01>) == PROBABILITY(|10>)", 2)


def test_amplitude_trailing_text_is_rejected() -> None:
    with pytest.raises(AssertionParseError, match="unexpected trailing text"):
        parse_one("PROBABILITY(|01>) == PROBABILITY(|10>) extra", 2)


# ---------------------------------------------------------------------------
# MEASURES — bare vs with-list, and the two-convention split (round-1 item 2)
# ---------------------------------------------------------------------------


def test_measures_bare_form_uses_the_shared_ket_convention() -> None:
    qc = QuantumCircuit(3)
    qc.x(0)
    qc.x(2)
    outcome = _one('MEASURES == "101"', 3, qc)
    assert outcome.passed is True


def test_measures_bare_form_false_case() -> None:
    qc = QuantumCircuit(3)
    qc.x(0)
    outcome = _one('MEASURES == "101"', 3, qc)
    assert outcome.passed is False


def test_measures_with_list_uses_positional_not_ket_convention() -> None:
    """Regression guard for the exact bug caught during implementation:
    `Statevector.probabilities_dict(qargs=...)`'s own string keys put the
    FIRST-listed qarg at the RIGHTMOST position — the opposite of what this
    grammar promises (`qubits[i]` <-> `expected[i]`, left to right). This
    circuit is deliberately asymmetric (q2=0, q0=1) so the two conventions
    give different, distinguishable answers instead of coincidentally
    agreeing on a palindromic case.
    """
    qc = _half_adder()
    text = 'INPUT(|0011>) THEN MEASURES([2,0]) == "01"'
    outcome = _one(text, 4, qc)
    assert outcome.passed is True
    # the wrong (qargs-dict) convention would have required "10" here instead
    wrong_convention = _one('INPUT(|0011>) THEN MEASURES([2,0]) == "10"', 4, qc)
    assert wrong_convention.passed is False


def test_measures_with_list_order_matters() -> None:
    qc = _half_adder()
    forward = _one('INPUT(|0011>) THEN MEASURES([2,0]) == "01"', 4, qc)
    reversed_ = _one('INPUT(|0011>) THEN MEASURES([0,2]) == "10"', 4, qc)
    assert forward.passed is True
    assert reversed_.passed is True  # both true because the lists were swapped consistently


def test_measures_qubit_list_duplicate_rejected() -> None:
    with pytest.raises(AssertionParseError, match="duplicate"):
        parse_one('MEASURES([0,0]) == "11"', 2)


def test_measures_qubit_out_of_range_rejected() -> None:
    with pytest.raises(AssertionParseError, match="out of range"):
        parse_one('MEASURES([0,5]) == "11"', 2)


def test_measures_bitstring_length_mismatch_rejected() -> None:
    with pytest.raises(AssertionParseError, match="length"):
        parse_one('MEASURES([0,1]) == "1"', 2)


def test_measures_empty_qubit_list_rejected() -> None:
    with pytest.raises(AssertionParseError, match="empty"):
        parse_one('MEASURES([]) == "1"', 2)


# ---------------------------------------------------------------------------
# EIGENSTATE_OF — residual-norm check, including the adversarial case
# ---------------------------------------------------------------------------


def test_eigenstate_true_case() -> None:
    qc = QuantumCircuit(1)  # |0> is the +1 eigenstate of Z
    outcome = _one('EIGENSTATE_OF("Z", 1)', 1, qc)
    assert outcome.passed is True


def test_eigenstate_false_case() -> None:
    qc = QuantumCircuit(1)
    qc.h(0)  # |+> is not an eigenstate of Z at all
    outcome = _one('EIGENSTATE_OF("Z", 1)', 1, qc)
    assert outcome.passed is False


def test_eigenstate_residual_norm_rejects_near_miss_that_expectation_alone_would_pass() -> None:
    """The whole reason this checks ||H|psi> - lambda|psi>|| rather than
    <psi|H|psi> == lambda (F2, report-notes.md): a state with population
    p=1e-10 leaked into the wrong eigenspace has a Z-expectation value
    within 2e-10 of +1 (i.e. indistinguishable from +1 at this codebase's
    own DEFAULT_TOL=1e-9), yet its residual norm is ~2e-5 — two orders of
    magnitude past the 1e-6 threshold. An expectation-only check would have
    passed this state; the residual-norm check correctly fails it.
    """
    p = 1e-10
    angle = 2 * math.asin(math.sqrt(p))
    qc = QuantumCircuit(1)
    qc.ry(angle, 0)

    sv = Statevector.from_instruction(qc)
    z_expectation = abs(sv.data[0]) ** 2 - abs(sv.data[1]) ** 2
    assert abs(1.0 - z_expectation) < 1e-9  # would fool an expectation-only check

    outcome = _one('EIGENSTATE_OF("Z", 1)', 1, qc)
    assert outcome.passed is False


def test_eigenstate_bad_eigenvalue_rejected() -> None:
    with pytest.raises(AssertionParseError):
        parse_one('EIGENSTATE_OF("ZZ", 2)', 2)


# ---------------------------------------------------------------------------
# QUBIT sugar — desugars to EigenstateAssertion, all six cardinal labels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "pauli_char", "eigenvalue"),
    [
        ("0", "Z", 1),
        ("1", "Z", -1),
        ("+", "X", 1),
        ("-", "X", -1),
        ("i", "Y", 1),
        ("-i", "Y", -1),
    ],
)
def test_qubit_sugar_desugars_correctly(label: str, pauli_char: str, eigenvalue: int) -> None:
    assertion = parse_one(f'QUBIT(1) == "|{label}>"', 3)
    assert assertion.kind == "eigenstate"
    assert assertion.eigenvalue == eigenvalue
    assert assertion.pauli_string == f"I{pauli_char}I"  # qubit 1 of 3, middle position


def test_qubit_sugar_evaluates_like_the_equivalent_eigenstate_of() -> None:
    qc = QuantumCircuit(2)
    qc.x(1)  # qubit 1 -> |1>, the -1 eigenstate of Z
    sugar = _one('QUBIT(1) == "|1>"', 2, qc)
    general = _one('EIGENSTATE_OF("ZI", -1)', 2, qc)
    assert sugar.passed is True
    assert sugar.passed == general.passed


def test_qubit_index_out_of_range_rejected() -> None:
    with pytest.raises(AssertionParseError, match="out of range"):
        parse_one('QUBIT(5) == "|0>"', 2)


# ---------------------------------------------------------------------------
# GATES_SUBSET_OF — structural, no INPUT, validated gate names
# ---------------------------------------------------------------------------


def test_gates_subset_true_case() -> None:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    outcome = _one('GATES_SUBSET_OF({"h", "cx"})', 2, qc)
    assert outcome.passed is True


def test_gates_subset_false_case() -> None:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.t(0)
    outcome = _one('GATES_SUBSET_OF({"h", "cx"})', 2, qc)
    assert outcome.passed is False
    assert "t" in outcome.detail


def test_gates_subset_unknown_gate_name_rejected() -> None:
    with pytest.raises(AssertionParseError, match="unknown gate name"):
        parse_one('GATES_SUBSET_OF({"h", "cxx"})', 2)


def test_gates_subset_empty_set_rejected() -> None:
    with pytest.raises(AssertionParseError, match="empty"):
        parse_one("GATES_SUBSET_OF({})", 2)


def test_gates_subset_input_prefix_rejected() -> None:
    with pytest.raises(AssertionParseError, match="purely structural"):
        parse_one('INPUT(|00>) THEN GATES_SUBSET_OF({"h"})', 2)


def test_gates_subset_typo_fails_closed_not_open() -> None:
    """The corrected rationale (see assertions.py/state.py docstrings): a
    subset-membership check is fail-closed by construction, so this isn't
    actually about preventing a vacuous pass — it's confirmed here that a
    circuit using a real, correctly-spelled gate still fails against a
    genuinely different allowed-set, i.e. there is no widening failure mode
    to begin with, typo'd or not."""
    qc = QuantumCircuit(1)
    qc.h(0)
    outcome = _one('GATES_SUBSET_OF({"x"})', 1, qc)
    assert outcome.passed is False


# ---------------------------------------------------------------------------
# INPUT(...) THEN <assertion> — non-trivial input, verified against a real
# oracle (reversible_half_adder_4q), not just a synthetic circuit.
# ---------------------------------------------------------------------------


def test_input_prefix_evaluates_against_prepared_state() -> None:
    qc = _half_adder()
    # a=1 (q0), b=1 (q1) -> sum=0 (q2), carry=1 (q3); ket convention leftmost
    # = q3: "1011".
    outcome = _one('INPUT(|0011>) THEN MEASURES == "1011"', 4, qc)
    assert outcome.passed is True


def test_input_prefix_distinguishes_different_inputs() -> None:
    qc = _half_adder()
    # a=1 (q0), b=0 -> sum=1, carry=0 -> "0101"
    outcome = _one('INPUT(|0001>) THEN MEASURES == "0101"', 4, qc)
    assert outcome.passed is True
    # the all-zero default input alone would not have caught a broken adder
    # that only works for a=b=0 — this is the "several INPUT assertions
    # give real probabilistic coverage" point from the design discussion.
    trivial = _one('MEASURES == "0000"', 4, qc)
    assert trivial.passed is True


def test_input_prefix_length_must_match_n_qubits() -> None:
    with pytest.raises(AssertionParseError, match="no implicit padding"):
        parse_one('INPUT(|011>) THEN MEASURES == "1011"', 4)


# ---------------------------------------------------------------------------
# Parsing — malformation paths not already covered above (FR-013)
# ---------------------------------------------------------------------------


def test_missing_comparator_rejected() -> None:
    with pytest.raises(AssertionParseError, match="comparator"):
        parse_one("PROBABILITY(|01>)", 2)


def test_ket_length_mismatch_rejected() -> None:
    with pytest.raises(AssertionParseError, match="no implicit padding"):
        parse_one("PROBABILITY(|0>) == 0.5", 2)


def test_unrecognized_form_rejected() -> None:
    with pytest.raises(AssertionParseError, match="unrecognized assertion form"):
        parse_one("nonsense", 2)


def test_empty_line_rejected() -> None:
    with pytest.raises(AssertionParseError, match="empty assertion"):
        parse_one("", 2)


def test_parse_assertions_refuses_the_whole_batch_on_one_bad_line() -> None:
    """FR-013: refused explicitly, never silently trimmed — one malformed
    line invalidates the entire batch rather than being dropped."""
    text = 'PROBABILITY(|00>) ~= 0.5\nGATES_SUBSET_OF({"cxx"})\nMEASURES == "01"'
    with pytest.raises(AssertionParseError, match="line 2"):
        parse_assertions(text, 2)


def test_parse_assertions_skips_blank_lines_and_comments() -> None:
    text = "\n# a comment\nPROBABILITY(|00>) ~= 1.0\n\n"
    assertions = parse_assertions(text, 2)
    assert len(assertions) == 1


def test_evaluate_assertions_reports_each_independently() -> None:
    """FR-011: one AssertionOutcome per input assertion, same order,
    regardless of whether earlier ones failed."""
    qc = _bell_phi_plus()
    text = 'PROBABILITY(|11>) ~= 0.5\nPROBABILITY(|01>) ~= 0.5\nMEASURES == "00"'
    assertions = parse_assertions(text, 2)
    outcomes = evaluate_assertions(assertions, qc)
    assert [o.passed for o in outcomes] == [True, False, False]


# ---------------------------------------------------------------------------
# Realistic generated code (found end to end, T092)
# ---------------------------------------------------------------------------


def test_final_measurements_do_not_block_state_assertions() -> None:
    """`measure_all()` samples the prepared state, it doesn't change it.
    Before the fix every state-based assertion raised QiskitError here and
    took the whole graph down."""
    qc = _bell_phi_plus()
    qc.measure_all()
    for text in (
        "PROBABILITY(|11>) ~= 0.5",
        "PHASE_DIFF(|00>,|11>) ~= 0",
        'EIGENSTATE_OF("ZZ", 1)',
        'QUBIT(0) == "|0>"',
    ):
        outcome = _one(text, 2, qc)
        assert outcome.passed is not None, f"{text}: {outcome.detail}"
    assert _one("PROBABILITY(|11>) ~= 0.5", 2, qc).passed is True


def test_mid_circuit_measurement_is_not_evaluable_not_a_crash() -> None:
    """A non-final measurement leaves no pure output state: the honest
    answer is "not evaluable", never an exception and never a verdict."""
    qc = QuantumCircuit(2, 1)
    qc.h(0)
    qc.measure(0, 0)
    qc.cx(0, 1)  # an operation AFTER the measurement makes it non-final
    outcome = _one("PROBABILITY(|11>) ~= 0.5", 2, qc)
    assert outcome.passed is None
    assert "no pure output state" in outcome.detail


def test_gate_restriction_ignores_non_gate_instructions() -> None:
    qc = _bell_phi_plus()
    qc.measure_all()  # adds `measure` and a `barrier`
    outcome = _one('GATES_SUBSET_OF({"h", "cx"})', 2, qc)
    assert outcome.passed is True, outcome.detail


def test_gate_restriction_still_catches_a_real_extra_gate_under_measurement() -> None:
    qc = _bell_phi_plus()
    qc.t(0)
    qc.measure_all()
    outcome = _one('GATES_SUBSET_OF({"h", "cx"})', 2, qc)
    assert outcome.passed is False
    assert "t" in outcome.detail and "measure" not in outcome.detail


def test_non_gate_instructions_match_qiskits_own_list() -> None:
    """Pins NON_GATE_INSTRUCTIONS to the installed Qiskit's
    BasisTranslator `basic_instrs` — the instructions Qiskit unions into
    every target basis. If a Qiskit upgrade changes that list, this fails
    instead of the two quietly drifting apart."""
    import ast
    import inspect

    import qiskit.transpiler.passes.basis.basis_translator as bt

    from qcagent.validators.assertions import NON_GATE_INSTRUCTIONS

    lists = [
        ast.literal_eval(node.value)
        for node in ast.walk(ast.parse(inspect.getsource(bt)))
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "basic_instrs" for t in node.targets)
    ]
    widest = max(lists, key=len)
    assert NON_GATE_INSTRUCTIONS == frozenset(widest)


@pytest.mark.parametrize(
    "text",
    [
        "PROBABILITY(|11>) ~= 0.5",
        "AMPLITUDE(|00>) == AMPLITUDE(|11>)",
        "PHASE_DIFF(|00>,|11>) ~= 0",
        'MEASURES == "01"',
        'MEASURES([1, 0]) == "01"',
        'EIGENSTATE_OF("ZI", -1)',
        'GATES_SUBSET_OF({"cx", "h"})',
        'INPUT(|01>) THEN MEASURES == "01"',
    ],
)
def test_render_assertion_round_trips_through_the_parser(text: str) -> None:
    """render_assertion names an assertion in the report, the critic prompt
    and the generator's diagnostic (FR-012) — so it must be the parser's
    exact inverse: parse(render(a)) == a."""
    from qcagent.validators.assertions import render_assertion

    (assertion,) = parse_assertions(text, 2)
    (reparsed,) = parse_assertions(render_assertion(assertion), 2)
    assert reparsed == assertion


# ---------------------------------------------------------------------------
# Register width — the user's assertions are the source of truth
# ---------------------------------------------------------------------------


def test_declared_register_widths_reads_every_full_register_form() -> None:
    from qcagent.validators.assertions import declared_register_widths

    text = (
        "PROBABILITY(|01>) ~= 0.5\n"
        "AMPLITUDE(|00>) == AMPLITUDE(|11>)\n"
        "PHASE_DIFF(|00>,|11>) ~= 0\n"
        'MEASURES == "10"\n'
        'EIGENSTATE_OF("ZZ", 1)\n'
        'INPUT(|01>) THEN MEASURES([0]) == "1"  # the INPUT ket counts\n'
    )
    assert declared_register_widths(text) == {2}


def test_declared_register_widths_ignores_index_only_and_gate_forms() -> None:
    """`QUBIT(1) == "|0>"` contains `|0>`, which a naive ket scan would read
    as a 1-qubit register."""
    from qcagent.validators.assertions import declared_register_widths

    text = 'QUBIT(1) == "|0>"\nMEASURES([1, 0]) == "01"\nGATES_SUBSET_OF({"h"})'
    assert declared_register_widths(text) == set()


def test_declared_register_widths_exposes_disagreement() -> None:
    from qcagent.validators.assertions import declared_register_widths

    assert declared_register_widths('PROBABILITY(|01>) ~= 0.5\nMEASURES == "010"') == {2, 3}


def test_minimum_register_width_from_indices() -> None:
    from qcagent.validators.assertions import minimum_register_width

    assert minimum_register_width('QUBIT(3) == "|+>"\nMEASURES([1, 5]) == "01"') == 6
    assert minimum_register_width("PROBABILITY(|01>) ~= 0.5") == 0


def _three_qubit_bell_like() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.h(0)
    qc.cx(0, 1)
    return qc


@pytest.mark.parametrize(
    "text",
    [
        "PROBABILITY(|11>) ~= 0.5",  # used to PASS by reading |011> instead
        'MEASURES == "11"',
        'EIGENSTATE_OF("ZZ", 1)',  # used to crash with a dimension error
        'QUBIT(1) == "|0>"',  # likewise
    ],
)
def test_circuit_wider_than_the_assertion_is_a_named_violation(text: str) -> None:
    """With the assertions defining the register, a circuit of a different
    width contradicts the user's statement. Evaluating anyway gave false
    passes (index 3 of a 3-qubit register is |011>, not |11>) or crashes."""
    outcome = _one(text, 2, _three_qubit_bell_like())
    assert outcome.passed is False
    assert outcome.detail == "assertion is written for 2 qubits but the circuit has 3"


def test_listed_qubit_beyond_the_circuit_is_a_named_violation_not_a_crash() -> None:
    outcome = _one('MEASURES([2, 0]) == "00"', 3, _bell_phi_plus())
    assert outcome.passed is False
    assert "measures qubit 2 but the circuit has only 2 qubits" in outcome.detail


def test_listed_qubits_within_a_wider_circuit_still_evaluate() -> None:
    """A marginal over in-range qubits is well-defined at any width, and the
    list form states no register width to contradict."""
    qc = QuantumCircuit(3)
    qc.x(1)
    outcome = _one('MEASURES([1]) == "1"', 2, qc)  # parsed for 2, evaluated on 3
    assert outcome.passed is True, outcome.detail


def test_width_free_gate_restriction_evaluates_at_any_width() -> None:
    assert _one('GATES_SUBSET_OF({"h", "cx"})', 2, _three_qubit_bell_like()).passed is True
