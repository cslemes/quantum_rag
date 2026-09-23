"""Tests for planner.py's `check_assertions` (T090): parsing `assertions_text`
before any generation, refusing what is genuinely malformed, and taking the
register width from the USER'S OWN ASSERTIONS rather than from the n_qubits
the planner LLM extracted.

The earlier rule validated assertions against the extracted count, so a
planner that misread a 2-qubit task as 3 refused a correct assertion as
"malformed" — the user's direct statement rejected because a model misread
the prompt (F3, F9). Decision recorded in tasks.md T090.
"""

from qcagent.nodes.planner import check_assertions
from qcagent.state import Requirement


def _n_qubits(value: int) -> list[Requirement]:
    return [Requirement(id="r1", kind="n_qubits", description="qubit count", value=value)]


# -- Basics -------------------------------------------------------------------


def test_no_assertions_text_returns_empty_with_no_rejection() -> None:
    reqs = _n_qubits(2)
    check = check_assertions(None, reqs)
    assert check.assertions == []
    assert check.rejection is None
    assert check.requirements == reqs


def test_blank_assertions_text_returns_empty_with_no_rejection() -> None:
    check = check_assertions("   \n  ", _n_qubits(2))
    assert check.assertions == []
    assert check.rejection is None


def test_well_formed_assertions_parse_successfully() -> None:
    check = check_assertions("PROBABILITY(|00>) ~= 0.5", _n_qubits(2))
    assert check.rejection is None
    assert [a.kind for a in check.assertions] == ["amplitude"]
    assert check.n_qubits_correction is None


def test_multiple_assertion_lines_all_parse() -> None:
    check = check_assertions('PROBABILITY(|00>) ~= 0.5\nMEASURES == "01"', _n_qubits(2))
    assert check.rejection is None
    assert len(check.assertions) == 2


def test_genuinely_malformed_assertion_is_still_refused() -> None:
    check = check_assertions('GATES_SUBSET_OF({"cxx"})', _n_qubits(2))
    assert check.assertions == []
    assert check.rejection is not None
    assert "malformed assertion" in check.rejection


# -- The assertions' width wins — when the evidence is strong enough -----------

_TWO_AGREEING = 'PROBABILITY(|11>) ~= 0.5\nMEASURES == "00"'


def test_one_assertion_contradicting_the_planner_is_refused_as_ambiguous() -> None:
    """One statement on each side: a misread description, or a typo in the
    one ket. Nothing breaks the tie, so the product asks instead of picking —
    a silent correction would let a one-character typo change the task."""
    check = check_assertions("PROBABILITY(|11>) ~= 0.5", _n_qubits(3))

    assert check.assertions == []
    assert check.n_qubits_correction is None
    assert check.rejection is not None
    assert check.rejection.startswith("ambiguous qubit count")
    assert "read as 3 qubits" in check.rejection
    assert "`PROBABILITY(|11>) ~= 0.5`, is written for 2" in check.rejection
    assert "malformed" not in check.rejection


def test_one_assertion_with_two_kets_is_still_one_statement() -> None:
    check = check_assertions("AMPLITUDE(|00>) == AMPLITUDE(|11>)", _n_qubits(3))
    assert check.rejection is not None
    assert check.rejection.startswith("ambiguous qubit count")


def test_two_agreeing_assertions_overrule_a_misread_planner_count() -> None:
    check = check_assertions(_TWO_AGREEING, _n_qubits(3))

    assert check.rejection is None
    assert len(check.assertions) == 2
    correction = check.n_qubits_correction
    assert correction is not None
    assert (correction.planner_n_qubits, correction.assertions_n_qubits) == (3, 2)
    assert correction.supporting_assertions == 2


def test_misread_n_qubits_requirement_is_corrected_not_left_to_veto() -> None:
    """Left at 3, the requirement would steer the generator to 3 qubits and
    then, through T091, veto the correct 2-qubit circuit — blaming the user a
    second time for the same extraction error."""
    check = check_assertions(_TWO_AGREEING, _n_qubits(3))

    (corrected,) = check.requirements
    assert corrected.value == 2
    assert "corrected: the planner read 3 qubits" in corrected.description


def test_other_requirements_are_untouched_by_the_correction() -> None:
    reqs = [
        *_n_qubits(3),
        Requirement(id="r2", kind="gate_set", description="h and cx", value=["h", "cx"]),
    ]
    check = check_assertions(_TWO_AGREEING, reqs)
    assert check.requirements[1] == reqs[1]


def test_width_from_assertions_needs_no_planner_count_at_all() -> None:
    """With nothing extracted there is nothing to contradict, so even a
    single assertion's width is simply used."""
    check = check_assertions("PROBABILITY(|000>) ~= 0.5", [])
    assert check.rejection is None
    assert len(check.assertions) == 1
    assert check.n_qubits_correction is None


def test_input_ket_counts_as_a_stated_width() -> None:
    check = check_assertions('INPUT(|011>) THEN MEASURES([0]) == "1"', [])
    assert check.rejection is None
    assert check.assertions[0].input_state == "011"
    # ...and it counts as a statement against the planner, like any other.
    assert check_assertions('INPUT(|011>) THEN MEASURES([0]) == "1"', _n_qubits(5)).rejection


def test_agreeing_planner_count_is_not_reported_as_a_correction() -> None:
    check = check_assertions("PROBABILITY(|11>) ~= 0.5", _n_qubits(2))
    assert check.rejection is None
    assert check.n_qubits_correction is None
    assert check.requirements[0].value == 2


# -- Assertions that disagree among themselves: that IS a user error -------------


def test_assertions_disagreeing_among_themselves_are_refused() -> None:
    check = check_assertions('PROBABILITY(|11>) ~= 0.5\nMEASURES == "010"', _n_qubits(2))
    assert check.assertions == []
    assert check.rejection is not None
    assert "disagree among themselves" in check.rejection
    assert "[2, 3]" in check.rejection


def test_index_out_of_range_for_the_users_own_width_names_the_source() -> None:
    check = check_assertions('PROBABILITY(|11>) ~= 0.5\nQUBIT(4) == "|0>"', _n_qubits(2))
    assert check.rejection is not None
    assert "from your own assertions" in check.rejection
    assert "QUBIT index 4 out of range for 2 qubits" in check.rejection


# -- Index-only assertions state no width ---------------------------------------


def test_index_only_assertions_that_fit_the_extracted_count_are_accepted() -> None:
    check = check_assertions('QUBIT(1) == "|+>"', _n_qubits(3))
    assert check.rejection is None
    assert check.assertions[0].pauli_string == "IXI"


def test_index_only_assertions_beyond_the_extracted_count_are_not_called_malformed() -> None:
    check = check_assertions('QUBIT(4) == "|0>"', _n_qubits(3))
    assert check.rejection is not None
    assert "malformed" not in check.rejection
    assert "none of them states the register width" in check.rejection
    assert "was read as 3 qubits" in check.rejection


def test_index_only_assertions_with_no_extracted_count_are_refused_with_the_reason() -> None:
    check = check_assertions('MEASURES([2, 0]) == "10"', [])
    assert check.rejection is not None
    assert "gave no qubit count" in check.rejection


def test_gate_set_only_assertions_need_no_width() -> None:
    check = check_assertions('GATES_SUBSET_OF({"h", "cx"})', [])
    assert check.rejection is None
    assert len(check.assertions) == 1
