"""Guarantee report (US4). See plan.md §Relatório de garantia and
data-model.md's §Linguagem de asserção for the fields this reads.

Principle II lives entirely in `GuaranteeReport.functional_correctness_
verified` and in `render_guarantee_report`'s wording, not in convention:
`functional_correctness_verified` is a `@computed_field` — never settable —
so a report claiming correctness it didn't earn is a construction-time
`ValidationError`, not a bug someone could introduce by passing the wrong
keyword. `render_guarantee_report` never phrases "executes and respects
constraints" as "correct" (FR-017), and states plainly, in every rendered
report with no verified assertions, that functional correctness was not
verified (FR-016) — see `tests/unit/test_report.py::
test_no_correctness_claim_without_verified_assertion` for the mandatory
test that would fail the build if either guarantee were ever violated.
"""

from pydantic import BaseModel, ConfigDict, computed_field

from qcagent.state import (
    AssertionOutcome,
    QubitCountCorrection,
    RequirementOutcome,
    ResourceResult,
    SemanticResult,
)
from qcagent.validators.assertions import render_assertion


class GuaranteeReport(BaseModel):
    """`extra="forbid"` plus `functional_correctness_verified` as a
    `@computed_field` (never a constructor argument) makes
    `GuaranteeReport(functional_correctness_verified=True, assertions=[])`
    a `ValidationError`, not a possible bug — see module docstring.
    """

    model_config = ConfigDict(extra="forbid")

    executed: bool
    transpiled: bool
    # T091 — replaces the earlier `requirements_checked: list[str]` stub,
    # which could only name requirements, never say whether they held. One
    # entry per CHECKABLE requirement (n_qubits/gate_set); requirements of
    # other kinds produce no entry at all, so an empty list means "nothing
    # here was checkable", never "everything passed" — the renderer says
    # which.
    requirements: list[RequirementOutcome]
    assertions: list[AssertionOutcome]  # empty iff none were declared
    # T090: set when two or more agreeing assertions overruled the qubit count
    # the planner read from the description. Rendered, not just traced: the
    # correction is evidence the extraction was wrong, and the reader of this
    # report is the one who can tell whether it was.
    n_qubits_correction: QubitCountCorrection | None
    # The reference comparison (semantic_check), present iff oracle_ref was.
    # Omitted from the first version of this report, which meant a
    # regression-suite run that PASSED exact unitary equivalence rendered
    # "nothing about its behavior was checked" next to status="success" —
    # F8's divergence in the other direction, and a false statement besides.
    reference: SemanticResult | None

    # Reference-free evidence (plan.md's "resources into the report, not
    # the grammar" decision, round-2 item 2): `coupling_map_name`/
    # `topology_respected` are None together iff no coupling_map was
    # declared at all — nothing to report, not a gap. When a coupling_map
    # WAS declared, `topology_respected` comes straight from `static.
    # transpiled`, unconditionally, whether or not a reference circuit
    # exists. `resource` (depth_ratio/cx_ratio) stays None unless
    # `oracle_ref` was present — `depth_ratio` genuinely has no meaning
    # without a reference (graph.py's resource_check requires one
    # unconditionally), and the renderer says so explicitly rather than
    # silently omitting the field.
    coupling_map_name: str | None
    topology_respected: bool | None
    resource: ResourceResult | None

    hardware_note: str | None  # US5 — "comportamento sob ruído", never "verification"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def functional_correctness_verified(self) -> bool:
        """FR-016: `bool(assertions)` short-circuits this to False when
        none were declared — the empty case is never accidentally treated
        as verified. `a.passed is True` (not truthy `a.passed`) so the
        tri-state `None` ("not evaluable") never counts as passing either
        — see `AssertionOutcome`'s own docstring in state.py.

        Requirements (T091) can VETO this but never ESTABLISH it, because
        of where they come from: a requirement is an LLM's reading of the
        description, so a PASSING one means only "the circuit agrees with
        what the planner read", which is not evidence of correctness. A
        FAILING one is stronger and asymmetric — whatever else holds, the
        circuit and the stated description disagree about something
        directly checkable, and no correctness claim should survive that.
        A `passed=None` requirement ("not checkable") vetoes nothing; it
        says the check never ran.

        This field is the ONE place "verified" is decided, for both paths:
        `routing.py::terminal_status` reads it rather than recomputing, so
        `status="success"` and this field cannot disagree. Order matters:

          1. No verification of a circuit that didn't execute and transpile.
             Nothing downstream can have run on it, so any outcome present
             would be stale — a structural guard, not a policy. (End to end,
             stale verdicts from an earlier attempt once produced VERIFIED
             about code that had failed to execute.)
          2. Any user-declared assertion that did not pass vetoes. The user's
             declaration outranks even a reference match.
          3. A FAILED reference comparison vetoes. The oracle is ground
             truth; passing assertions are partial properties and cannot
             outrank it saying the circuit is wrong. (Missing from the first
             version of this ordering, which let a circuit that failed its
             reference but passed its assertions come out VERIFIED — caught
             by a unit test written for a different branch.)
          4. A passed reference comparison verifies. Because it is ground
             truth (Principle IV), a failing REQUIREMENT does not veto it:
             when an oracle and a planner-extracted requirement disagree, the
             planner was wrong.
          5. Otherwise a failed requirement vetoes, and verification needs
             at least one declared assertion (all of which passed, by 2).
        """
        if not (self.executed and self.transpiled):
            return False
        if any(a.passed is not True for a in self.assertions):
            return False
        if self.reference is not None:
            return self.reference.passed
        if any(r.passed is False for r in self.requirements):
            return False
        return bool(self.assertions)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def only_trivial_input_tested(self) -> bool:
        """True when at least one input-capable assertion was declared and
        NONE of them used `INPUT(...)` — a purely structural fact, always
        rendered when true (approved design decision: no attempt to guess
        whether the underlying task is a "general transformation", which
        would require judgment this deterministic path cannot make;
        Principle I). `GateRestrictionAssertion` has no `input_state` field
        at all (structural, not state-dependent) and is excluded from the
        count on either side.
        """
        input_capable = [
            o.assertion for o in self.assertions if hasattr(o.assertion, "input_state")
        ]
        return bool(input_capable) and not any(a.input_state is not None for a in input_capable)


def _render_requirements_section(report: GuaranteeReport) -> list[str]:
    """T091. An empty list is rendered as "none checked", with the reason —
    never as a bare "none", which reads as "we checked and found none" and
    borrows a verification verb for a check that didn't happen.
    """
    if not report.requirements:
        return [
            "Requirements: none checked — no qubit-count or gate-set requirement was "
            "extracted from the description (those are the only two checkable without "
            "a reference circuit)."
        ]
    n_passed = sum(1 for r in report.requirements if r.passed is True)
    lines = [f"Requirements ({n_passed}/{len(report.requirements)} passed):"]
    for outcome in report.requirements:
        label = (
            "PASS"
            if outcome.passed is True
            else "NOT_CHECKABLE"
            if outcome.passed is None
            else "FAIL"
        )
        lines.append(f"  [{label}] {outcome.requirement.kind} — {outcome.detail}")
    return lines


def _render_assertions_section(report: GuaranteeReport) -> list[str]:
    if not report.assertions:
        return ["Assertions: none declared."]

    n_passed = sum(1 for o in report.assertions if o.passed is True)
    lines = [f"Assertions ({n_passed}/{len(report.assertions)} passed):"]
    for outcome in report.assertions:
        rendered = render_assertion(outcome.assertion)
        if outcome.passed is True:
            lines.append(f"  [PASS] {rendered}")
        elif outcome.passed is None:
            lines.append(f"  [NOT_EVALUABLE] {rendered} — {outcome.detail}")
        else:
            lines.append(f"  [FAIL] {rendered} — {outcome.detail}")

    if report.only_trivial_input_tested:
        n = len(report.assertions)
        coverage = f"all {n} assertions" if n > 1 else "the assertion"
        lines.append("")
        lines.append(
            f"Input coverage: only the |0...0> input was exercised across {coverage}. "
            "If this circuit is meant to implement a general transformation, no "
            "assertion here confirms behavior on other inputs."
        )
    return lines


def _render_topology_section(report: GuaranteeReport) -> list[str]:
    lines: list[str] = []
    if report.topology_respected is not None:
        respects = "respects" if report.topology_respected else "does NOT respect"
        lines.append(
            f"Topology: {respects} the declared coupling map ({report.coupling_map_name}) — "
            "verified by successful transpilation, independent of any assertion result above."
        )
    # Rendered whenever a resource result EXISTS, not only when a coupling map
    # was declared. An earlier version nested this under the topology branch,
    # so a regression-suite run cut off on resources with no coupling map
    # (resource_check falls back to all-to-all) rendered VERIFIED and never
    # showed the resource result that ended the run — found end to end, T098.
    if report.resource is not None:
        r = report.resource
        verdict = "within" if r.passed else "EXCEEDS"
        lines.append(
            f"Resource: depth_ratio={r.depth_ratio:.2f}, cx_ratio={r.cx_ratio:.2f} "
            f"({verdict} the configured limit)"
        )
    elif report.topology_respected is not None:
        lines.append(
            "Resource/depth ratio: not evaluated — no reference circuit is available in "
            "this run, and depth_ratio has no meaning without one."
        )
    return lines


def _describe_reference(ref: SemanticResult) -> str:
    """What a PASSED reference comparison actually established. Per method,
    because the methods do not prove the same thing, and a report that said
    "matches the reference" for all of them would over-claim for every one
    but the exact check: composition is probabilistic (D3b), a statevector
    oracle only fixes the output from |0...0> (D3c), and distribution/energy
    checks say nothing about the state or the unitary."""
    method = ref.verification_method
    if method == "exact":
        return (
            "it is unitarily equivalent to a verified reference circuit (exact check, "
            "up to global phase)"
        )
    if method == "composition":
        return (
            "it is equivalent to a verified reference circuit, checked by composition on "
            "random input states — a probabilistic check, not an exact one"
        )
    if method == "statevector":
        return (
            "it prepares the same output state as a verified reference circuit, starting "
            "from |0...0> only — its behavior on other inputs was not compared"
        )
    if ref.hellinger_fidelity is not None:
        return (
            "its measured output distribution matches a verified reference (Hellinger "
            f"fidelity {ref.hellinger_fidelity:.4f}) — a distributional check, not state "
            "or unitary equivalence"
        )
    if ref.energy_error is not None:
        return (
            f"its energy matches a verified value (error {ref.energy_error:.4g}) — an "
            "energy check, not state or unitary equivalence"
        )
    return "it matches a verified reference"


def _render_verdict(report: GuaranteeReport) -> str:
    reference_passed = report.reference is not None and report.reference.passed
    if report.functional_correctness_verified:
        if not reference_passed:
            return (
                f"FUNCTIONAL CORRECTNESS: VERIFIED — all {len(report.assertions)} declared "
                "assertions passed. This means the circuit satisfies every property you "
                "declared; it does NOT mean the circuit is correct in any sense beyond "
                "those properties."
            )
        assert report.reference is not None
        grounds = [_describe_reference(report.reference)]
        if report.assertions:
            grounds.append(f"all {len(report.assertions)} declared assertions passed")
        return (
            f"FUNCTIONAL CORRECTNESS: VERIFIED — {'; and '.join(grounds)}. It does NOT "
            "mean the circuit is correct in any sense beyond what was checked."
        )

    # A circuit that didn't execute or transpile had nothing checked on it.
    # Without this branch the no-assertions text below would say "the
    # circuit executing successfully" about code that did not execute.
    if not report.executed or not report.transpiled:
        failed_at = "execute" if not report.executed else "transpile"
        return (
            f"FUNCTIONAL CORRECTNESS: NOT VERIFIED — the final circuit did not {failed_at}, "
            "so nothing about its behavior could be checked."
        )

    # Checked before the assertion branches: a failed requirement vetoes the
    # claim no matter how the assertions came out (see
    # `functional_correctness_verified`), so it is the operative reason and
    # must be the one stated.
    n_failed_reqs = sum(1 for r in report.requirements if r.passed is False)
    # Product path only: with a reference present, the reference decides (a
    # pass verifies regardless of requirements; a failure is the stronger
    # reason to state, and is stated below).
    if n_failed_reqs and report.reference is None:
        return (
            f"FUNCTIONAL CORRECTNESS: NOT VERIFIED — the circuit does not meet "
            f"{n_failed_reqs} requirement(s) read from your own description (listed "
            "below). Whatever else holds, the circuit and the description disagree "
            "about something directly checkable."
        )

    n_failed = sum(1 for o in report.assertions if o.passed is False)
    n_not_evaluable = sum(1 for o in report.assertions if o.passed is None)
    if n_failed or n_not_evaluable:
        bits = []
        if n_failed:
            bits.append(f"{n_failed} failed")
        if n_not_evaluable:
            bits.append(f"{n_not_evaluable} not evaluable")
        return (
            f"FUNCTIONAL CORRECTNESS: NOT VERIFIED — {', '.join(bits)} of "
            f"{len(report.assertions)} declared assertions. The circuit executing and "
            "respecting the declared constraints is NOT evidence of functional correctness."
        )

    if report.reference is not None:
        # Every assertion (if any) passed, so the reference must have FAILED —
        # a passing one would have verified above. Behavior WAS checked here,
        # which is why the no-assertions text below would be false.
        reason = report.reference.error.message if report.reference.error else "no match"
        return (
            "FUNCTIONAL CORRECTNESS: NOT VERIFIED — the circuit does not match the verified "
            f"reference ({reason}). The circuit executing and respecting the declared "
            "constraints is NOT evidence of functional correctness."
        )

    if not report.assertions:
        # FR-016 — stated plainly, not left to be inferred from the absence
        # of an "Assertions" list below.
        return (
            "FUNCTIONAL CORRECTNESS: NOT VERIFIED. No assertions were declared for this "
            "circuit, so nothing about its behavior was checked. The circuit executing "
            "successfully and satisfying the requirements below is NOT evidence that it "
            "does what you intended — only that it runs and respects the constraints you "
            "stated. If you want functional correctness verified, add assertions "
            "describing what the circuit should do."
        )

    # Executed and transpiled, no failing assertion, no reference, no failed
    # requirement, at least one assertion: that is exactly "verified", handled
    # at the top. Reaching here means the two functions have drifted apart —
    # fail loudly rather than render a verdict sentence that fits nothing.
    raise AssertionError(
        "unreachable verdict state — _render_verdict and "
        "functional_correctness_verified have diverged"
    )


def render_guarantee_report(report: GuaranteeReport) -> str:
    """T094 — FR-011/FR-015: every assertion enumerated with its own
    verdict. FR-016: explicit non-verification statement whenever
    `functional_correctness_verified` is False. FR-017: never renders
    "executes and respects constraints" as a synonym for "correct" — see
    `_render_verdict` and `tests/unit/test_report.py` for the vocabulary
    check that holds this line, not just style convention.
    """
    # The verdict leads, before any of the affirmative-looking facts below.
    # Ordering it last (as an earlier version did) put three "yes"-shaped
    # lines — Executed/Transpiled/Requirements — ahead of it, which is the
    # exact shape that produces optimistic skimming: a reader who stops
    # early would have seen only good news. The one line that must not be
    # missed goes where it cannot be.
    lines = ["=== Guarantee Report ===", "", _render_verdict(report), ""]

    lines.append("--- What was and was not checked ---")
    lines.append(f"Executed: {'yes' if report.executed else 'no'}")
    if report.coupling_map_name is not None:
        lines.append(
            f"Transpiled: {'yes' if report.transpiled else 'no'} "
            f"(coupling map: {report.coupling_map_name})"
        )
    else:
        lines.append(f"Transpiled: {'yes' if report.transpiled else 'no'}")
    if report.n_qubits_correction is not None:
        c = report.n_qubits_correction
        lines.append(
            f"Qubit count: {c.assertions_n_qubits}, taken from {c.supporting_assertions} of "
            f"your assertions — the description was read as {c.planner_n_qubits} qubits. "
            "If that reading was right, your assertions describe a different circuit than "
            "the one you asked for."
        )
    lines.append("")
    if report.reference is not None:
        ref = report.reference
        if ref.passed:
            lines.append(f"Reference comparison: PASSED — {_describe_reference(ref)}.")
        else:
            reason = ref.error.message if ref.error else "no match"
            lines.append(f"Reference comparison: FAILED — {reason}")
        lines.append("")
    lines.extend(_render_requirements_section(report))
    lines.append("")
    lines.extend(_render_assertions_section(report))
    topology_lines = _render_topology_section(report)
    if topology_lines:
        lines.append("")
        lines.extend(topology_lines)
    if report.hardware_note is not None:
        lines.append("")
        lines.append(f"Hardware: {report.hardware_note}")
    return "\n".join(lines)
