"""The interface cannot make an unverified run look approved (US6, FR-024).

`test_report.py` holds this line for the TEXT report via a vocabulary check.
A UI needs its own, and a stricter one: colour and iconography are read
pre-attentively, before any sentence is parsed, so a green check beside
"Executed: yes" lands before the verdict does and no wording downstream
undoes it.

Two rules are enforced here rather than agreed:

* a checkmark and success colour are VERDICT glyphs — never spent on a
  sub-fact, because that borrows the verdict's authority for a fact that is
  not the verdict (FR-017: executing is not a synonym for correct);
* the positive verdict ENUMERATES what passed. A lone "VERIFIED" overclaims:
  what was verified is N specific assertions, not correctness in general.

These read the shipped page rather than a copy of it, so the check cannot
drift from what a user sees.
"""

import re
from pathlib import Path

PAGE = Path("src/qcagent/ui/static/index.html").read_text()


def _render_done_source() -> str:
    """The branch of the client that turns a finished run into the verdict."""
    start = PAGE.index("function renderDone(")
    return PAGE[start : PAGE.index("\n}", start)]


def test_the_unverified_branch_never_emits_a_checkmark() -> None:
    """A check is the verdict's glyph. If it appears at all in the page, it
    must not be reachable from the unverified path."""
    assert "✓" not in PAGE and "&check;" not in PAGE, (
        "a checkmark in the page can be read as approval before the words are; "
        "the verdict is carried by the container and the sentence instead"
    )


def test_sub_facts_render_as_neutral_marks_not_verdicts() -> None:
    """Executed/Transpiled use a separator, never a pass/fail glyph or the
    success colour — this is the visual form of FR-017."""
    source = _render_done_source()
    assert "Executed · " in source and "Transpiled · " in source, (
        "sub-facts must use neutral typography; a check or success colour here "
        "would lend them the verdict's authority"
    )


def test_the_verified_verdict_names_the_assertion_count() -> None:
    """A bare VERIFIED overclaims. The text report already enumerates; the UI
    must too, or the UI is the weaker of the two."""
    source = _render_done_source()
    verified_branch = source[source.index("if (verified)") : source.index("} else if")]

    assert "rep.assertions.length" in verified_branch, "the count must come from the data"
    assert "declared assertion" in verified_branch
    assert "does <strong>not</strong>" in verified_branch, (
        "the verified case must still bound its own claim, as the text report does"
    )


def test_the_code_panel_carries_its_own_verdict() -> None:
    """Screenshotting or scrolling to just the code is the realistic misuse,
    so the banner travels WITH the code rather than living only in the report
    above it."""
    source = _render_done_source()
    assert "codehead" in source
    assert "NOT VERIFIED — nothing checked whether this does what you asked" in source


def test_the_no_assertions_case_says_nothing_was_checked() -> None:
    """The case Principle II exists for: the code ran, so every affirmative
    sub-fact is true, and yet nothing about correctness was established."""
    source = _render_done_source()
    branch = source[source.index("rep.assertions.length === 0") :]
    assert "NOT VERIFIED — nothing was checked" in branch
    assert "nothing checked whether it does what you asked" in branch
    assert "Add an assertion" in branch, "state the action that would make a verdict possible"


def test_max_iter_reads_as_a_decision_not_a_crash() -> None:
    assert "declined to claim success" in PAGE
    assert "Stopped after ${d.max_iter} attempts without verifying correctness" in PAGE


def test_the_reference_base_rate_appears_only_after_a_failure() -> None:
    """The 1.8% success rate was measured over a deliberately hard reference
    suite with perturbed variants. It explains a failure; it does NOT predict
    anything about a task a user writes, and showing it before submission
    would be using a measurement outside its regime (F19)."""
    source = _render_done_source()
    stopped = source[source.index("const stopped") : source.index('$("right").innerHTML')]

    assert "reference suite" in stopped
    assert "not a prediction for" in stopped, "label what the number is and is not"
    # It must not be reachable from anything that renders before a result.
    before = PAGE[: PAGE.index("function renderDone(")]
    assert "reference suite" not in before


def test_the_verdict_is_read_from_the_report_never_recomputed() -> None:
    """`functional_correctness_verified` is decided in report.py and everything
    else reads it. Two bugs (F8, F10) established that invariant; a UI that
    re-derived the verdict from executed/transpiled would be the third."""
    source = _render_done_source()
    assert "const verified = rep && rep.verified;" in source
    assert not re.search(r"verified\s*=\s*.*executed", source), (
        "the verdict must not be re-derived from sub-facts in the client"
    )


# --- the distribution is descriptive, never evaluative (FR-018) ------------


def _distribution_source() -> str:
    start = PAGE.index("function distributionHtml(")
    return PAGE[start : PAGE.index("\n}", start)]


def test_the_distribution_uses_no_verdict_colour() -> None:
    """Someone seeing 50/50 on |000> and |111> will infer correctness on their
    own. The system must not appear to be making that claim, so no bar, label
    or border in this panel may use the success colour — FR-017 in a new
    place."""
    source = _distribution_source()

    assert "--verified" not in source
    assert "verified" not in source.replace("NOT VERIFIED", ""), (
        "the distribution panel must not reference the verdict at all"
    )
    # The only colour the bars use is the same grey as borders.
    assert "var(--line)" in PAGE[PAGE.index(".bar {") : PAGE.index(".bar {") + 200]


def test_the_distribution_is_rendered_outside_the_guarantee_card() -> None:
    """Inside the card it would read as part of the claim."""
    done = _render_done_source()
    card_end = done.index("${stopped}")
    assert "distributionHtml" not in done[:card_end], (
        "the observation must not be nested in the verdict's container"
    )
    assert "distributionHtml" in done


def test_the_panel_says_it_is_an_observation() -> None:
    source = _distribution_source()
    assert "an observation, not a verdict" in source


def test_exact_and_sampled_are_distinguished_rather_than_blurred() -> None:
    """They are different claims: one has shot noise and the other does not."""
    source = _distribution_source()
    assert "not sampled, so there is no shot noise" in source
    assert "8192 shots" in source


def test_truncation_states_the_omitted_mass() -> None:
    """Silently dropping outcomes would misrepresent the circuit."""
    assert "omitted_probability" in _distribution_source()


def test_the_draft_assertion_comes_from_the_server() -> None:
    """The browser must never construct grammar: a second, more forgiving
    generator would drift from the parser (F11). The server builds the draft
    with the same code that can check it."""
    source = PAGE[PAGE.index("function wireDrafts(") :]
    assert "dist.outcomes[+btn.dataset.draft].draft" in source
    assert "PROBABILITY(" not in source, "no grammar construction in the client"


def test_clicking_a_draft_sizes_the_kets_for_that_circuit() -> None:
    """No implicit padding in the grammar (bug 10), so a draft pasted at the
    wrong qubit count would be refused."""
    source = PAGE[PAGE.index("function wireDrafts(") :]
    assert '$("nq").value = dist.n_qubits' in source
