"""Graph state and its Pydantic entities. See data-model.md."""

from operator import add
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field, StrictInt


class Requirement(BaseModel):
    """Verifiable requirement extracted by the planner. Becomes the critic's contract."""

    id: str
    kind: Literal["n_qubits", "gate_set", "property", "resource", "output_format"]
    description: str
    # StrictInt, not int: this is the planner (LLM) output boundary, where
    # malformed input must be refused rather than interpreted. Lax `int`
    # silently turned `"value": true` into a 1-qubit requirement (and
    # `false` into a 0-qubit one) that T091 then CHECKED, and accepted
    # `3.0` while already refusing `2.5` — an inconsistent rule, floats
    # passing only when they happened to be integral. The planner's own
    # declared contract is `string | integer | array of string | null`;
    # StrictInt enforces exactly that. Verified before switching: the only
    # inputs whose outcome changes are bool and integral float, both out of
    # contract; the one recorded real planner response (qwen2.5-coder:7b)
    # emits a true int. A refused value raises out of `_parse_planner_
    # response`, the same path an unknown `kind` already takes.
    value: str | StrictInt | list[str] | None = None


# -- US3 assertion language (spec.md FR-010-013; plan.md §Verificação sem
# referência has the full grammar). Every ket/Pauli string below shares ONE
# convention, stated once here rather than per class: leftmost character =
# highest-indexed qubit, rightmost = qubit 0 — identical to Qiskit's own
# `Statevector.probabilities_dict()`/`Pauli` label convention, chosen
# specifically so nothing new has to be learned on top of what a Qiskit user
# already knows (this project has hit the cost of an undeclared/mismatched
# convention three times before landing here — D3c, D3d, D3f). No implicit
# padding: a ket or Pauli string's length always equals `n_qubits`, with one
# deliberate exception — see `MeasuresAssertion.qubits`/`expected` below,
# which uses a SEPARATE, explicitly different convention on purpose (see
# `validators/assertions.py`'s module docstring for why unifying the two
# would be worse, not better).


class AmplitudeTerm(BaseModel):
    """One operand of an `AmplitudeAssertion` comparison.

    `probability`/`amplitude` read `Statevector[basis_state]` and return
    `|psi|**2`/`|psi|` respectively — always defined, magnitude-only,
    global-phase-blind by construction (same reasoning as D3c: phase alone
    is never comparable between two otherwise-correct implementations).

    `phase_diff` is the ONLY way this grammar exposes phase information, and
    only in the one form that's actually physically well-posed: the relative
    phase between two amplitudes, `arg(psi[basis_state_b]) -
    arg(psi[basis_state])`, mod 2*pi. A bare "phase of one ket" is
    deliberately NOT expressible — it isn't a real observable by itself, only
    a DIFFERENCE between two is. `phase_diff` is undefined whenever either
    amplitude is ~0 (no phase to speak of); evaluating it then produces
    `AssertionOutcome.passed=None` ("not evaluable"), never a false pass or
    fail — see `validators/assertions.py`.
    """

    kind: Literal["probability", "amplitude", "phase_diff"]
    basis_state: str
    basis_state_b: str | None = None  # required iff kind == "phase_diff", else must be None


class AmplitudeAssertion(BaseModel):
    """`PROBABILITY(...)`/`AMPLITUDE(...)`/`PHASE_DIFF(...)` on either side of
    a comparator. `rhs` being another `AmplitudeTerm` (not just a number) is
    what makes pairwise comparisons like `AMPLITUDE(a) == AMPLITUDE(b)`
    possible without a second assertion kind — parser enforces `lhs.kind ==
    rhs.kind` when `rhs` is a term (comparing a probability to a magnitude is
    a type mismatch, not a legitimate assertion — caught at parse time, not
    silently accepted).
    """

    kind: Literal["amplitude"] = "amplitude"
    lhs: AmplitudeTerm
    comparator: Literal["==", "~=", ">=", "<="]
    rhs: AmplitudeTerm | float
    input_state: str | None = None  # INPUT(...) prefix; None = |0...0> (no prep stage)


class MeasuresAssertion(BaseModel):
    """`MEASURES(...) == "<bitstring>"` — asserts the marginal probability of
    the stated outcome is ~1 (deterministic), never a partial/threshold
    probability (use `AmplitudeAssertion` with `PROBABILITY` for that).

    `qubits=None` is the BARE form (`MEASURES == "101"`, no parens) — the
    full register, in this module's ONE shared convention (leftmost =
    highest qubit). `qubits=[...]` is the WITH-LIST form — REQUIRED for any
    subset, and uses positional correspondence between `qubits` and
    `expected` instead (`qubits[i]` measures to `expected[i]`) — a
    deliberately DIFFERENT convention from the bare form, because once
    `qubits` is an arbitrary user-chosen subset/order, "leftmost = highest
    index" stops being well-defined; positional correspondence to an
    explicit list is the only convention that still makes sense. The two
    forms are syntactically distinct (parens or not) specifically so this
    split can never collide inside one written assertion.
    """

    kind: Literal["measures"] = "measures"
    qubits: list[int] | None = None
    expected: str
    input_state: str | None = None


class EigenstateAssertion(BaseModel):
    """`EIGENSTATE_OF("<pauli_string>", <+1|-1>)` — the general form.
    `QUBIT(q) == "|label>"` (one of the six Bloch-sphere cardinal states) is
    pure syntactic sugar for this class, desugared at PARSE time in
    `validators/assertions.py` (never a separate runtime kind) — this is
    what keeps `EIGENSTATE_OF` the one real evaluation path for both.

    Checked via the residual norm `||H|psi> - eigenvalue|psi>||`, NEVER via
    `<psi|H|psi> == eigenvalue` alone — a correct expectation value does not
    imply the state actually IS an eigenstate (a superposition of eigenstates
    whose eigenvalues average to the right number would pass the weaker
    check). This is F2 (report-notes.md — a measurement-based check can be
    structurally blind, not just loose) applied preventively to a checker
    that didn't exist yet, rather than discovered via a production bug.
    """

    kind: Literal["eigenstate"] = "eigenstate"
    pauli_string: str
    eigenvalue: Literal[1, -1]
    input_state: str | None = None


class GateRestrictionAssertion(BaseModel):
    """`GATES_SUBSET_OF({"h", "cx", ...})` — purely structural (over
    `circuit.data`), never simulated, so it has no `input_state`: an INPUT
    prefix on this form is a parse-time malformation, not silently ignored —
    gate vocabulary doesn't depend on what state the circuit is evolved
    from. Gate names are exactly Qiskit's own lowercase instruction-name
    strings (`operation.name`), not a separate vocabulary — an unknown name
    is rejected at parse time (FR-013).

    Correction versus an earlier draft of this design: a typo'd gate name
    does NOT make this assertion vacuously pass (a subset-membership check
    is fail-closed by construction — a circuit that genuinely uses the
    intended, correctly-spelled gate would fail against a typo'd set, not
    pass). Validating the name at parse time is worth doing anyway, for a
    more modest, honest reason: it turns a typo into an immediate, precise
    parse error ("unknown gate name") instead of a confusing downstream
    assertion failure that looks like a defect in the CIRCUIT rather than
    in the ASSERTION that named a gate which doesn't exist.
    """

    kind: Literal["gate_restriction"] = "gate_restriction"
    allowed_gates: frozenset[str]


Assertion = Annotated[
    AmplitudeAssertion | MeasuresAssertion | EigenstateAssertion | GateRestrictionAssertion,
    Field(discriminator="kind"),
]


class AssertionOutcome(BaseModel):
    """Result of evaluating one `Assertion` (FR-011: reported individually,
    never merged). `passed=None` means "not evaluable", in exactly two
    cases: a `phase_diff` term against a zero-amplitude basis state, and
    any state-based assertion against a circuit with a non-final
    measurement, reset or other non-unitary instruction (no pure output
    state exists; final measurements are stripped first and do NOT cause
    this). The second case was found by the first end-to-end run (T092).
    `GATES_SUBSET_OF` always resolves to True or False. `None` is never
    treated as truthy: `GuaranteeReport.functional_correctness_verified`
    (report.py, US4) requires `passed is
    True` on every assertion, explicitly — an unevaluated assertion must
    never silently count toward a correctness claim (Principio II).
    """

    assertion: Assertion
    passed: bool | None
    detail: str


class RequirementOutcome(BaseModel):
    """Result of checking one planner-extracted `Requirement` against the
    generated circuit (FR-009, T091) — deliberately NOT an
    `AssertionOutcome`, despite the identical shape, because the two have
    different PROVENANCE and therefore different evidential weight: an
    assertion is what the USER declared, a requirement is what an LLM
    extracted from the description. `report.py` keeps them in separate
    fields for the same reason, and `GuaranteeReport.
    functional_correctness_verified` lets a requirement failure VETO a
    correctness claim but never ESTABLISH one (see that field's docstring).

    `passed=None` means "not checkable" — the requirement's `value` isn't
    in a form this checker can evaluate (a non-integer `n_qubits`, a
    `gate_set` naming instructions Qiskit doesn't have). Same tri-state
    discipline as `AssertionOutcome`: never a forced verdict, never a
    silent drop. Requirements of a `kind` this checker doesn't handle
    (`property`, `output_format`, `resource`) produce NO outcome at all —
    they are out of scope, and emitting a passing outcome for them would
    claim a check that never happened.
    """

    requirement: Requirement
    passed: bool | None
    detail: str


class QubitCountCorrection(BaseModel):
    """The planner's extracted qubit count was overruled by the user's own
    assertions (T090). Only ever built when TWO OR MORE assertions state the
    same width — a single assertion disagreeing with the planner is refused
    as ambiguous instead (planner.py::check_assertions). Carried into the
    guarantee report, not only the trace: the correction is evidence the
    extraction was wrong, and the person reading the report is the one who
    can tell whether it was."""

    planner_n_qubits: int
    assertions_n_qubits: int
    supporting_assertions: int


class Chunk(BaseModel):
    doc_id: str
    text: str
    source: Literal["qiskit_api", "pennylane_api", "arxiv", "migration_guide"]
    library_version: str | None = None
    deprecated: bool = False  # FR-014: labeled, not omitted
    replacement: str | None = None  # what to use instead
    score: float


# The closed error taxonomy, as DATA rather than as prose spread across
# three files (data-model.md's table, static.py's classifier, critic.py's
# routing sets). Bug 20: `NonUnitaryCircuit` was added to the table and to
# the validator that emits it, but not to the routing sets — and the gap only
# surfaced two hours into a live run, as
# `ValueError: unroutable error_type 'NonUnitaryCircuit'`. The guard that
# raised was working exactly as designed; what was missing was anything that
# checked the three lists agree BEFORE a run.
#
# `tests/unit/test_taxonomy_closed.py` walks this set against both the
# routing table and the spec, so adding an entry in one place and forgetting
# the others fails in CI instead of in production.
ERROR_TAXONOMY = frozenset(
    {
        "DeprecatedAPI",
        "HallucinatedSymbol",
        "MissingImport",
        "SyntaxError",
        "TranspilationFailure",
        "CircuitSerializationFailure",
        "QubitIndexError",
        "MissingMeasurement",
        "ParameterBindingError",
        "EndiannessSwap",
        "WrongGateDecomposition",
        "ConceptualAlgorithmError",
        "NonUnitaryCircuit",
        "AssertionViolated",
        "AssertionNotEvaluable",
        "ResourceExcess",
    }
)


class ErrorRecord(BaseModel):
    iteration: int
    # "planner" errors never reach the critic: by the time one exists there
    # are no requirements to repair against, so the graph goes straight to a
    # terminal status. It is recorded as an ErrorRecord anyway so the failure
    # is COUNTABLE in the results file — a failure mode that only appears in
    # a trace nobody persists is a failure mode nobody measures.
    #
    # "harness" is the one value the GRAPH never produces: it is written by
    # bench/runner.py when a run raised an unexpected exception, so the
    # defect is recorded in the same shape as every other error instead of
    # needing a parallel channel. Nothing routes on it — by the time it
    # exists, the run is already over.
    stage: Literal["static", "semantic", "resource", "planner", "harness"]
    error_type: str  # closed taxonomy — see data-model.md
    message: str  # truncated traceback or formatted diff
    payload: dict = Field(default_factory=dict)


class StaticResult(BaseModel):
    parsed: bool
    executed: bool
    transpiled: bool
    circuit_qpy: bytes | None = None
    error: ErrorRecord | None = None


class SemanticResult(BaseModel):
    # None whenever oracle_kind isn't "unitary" — a statevector-oracle circuit
    # can pass this check's target (see D3c, research.md) while still being
    # unitarily inequivalent (e.g. GHZ via a CX chain vs a CX star), so
    # `unitary_equiv=True` must never be inferred from `passed=True` alone.
    unitary_equiv: bool | None = None
    # None whenever oracle_kind isn't "statevector" (D3c) — the state-only
    # counterpart to unitary_equiv, for oracle_kind="unitary" this stays None
    # even when the check happens to pass.
    state_equiv: bool | None = None
    verification_method: Literal["exact", "composition", "statevector"] | None = None
    endianness_swapped: bool = False  # FR-005: its own category
    hellinger_fidelity: float | None = None
    hellinger_std: float | None = None  # deviation across seeds
    tvd: float | None = None
    energy_error: float | None = None
    passed: bool = False
    error: ErrorRecord | None = None


class ResourceResult(BaseModel):
    depth: int
    cx_count: int
    width: int
    depth_ratio: float  # generated / reference, SAME transpiler
    cx_ratio: float
    passed: bool


class CriticDecision(BaseModel):
    action: Literal["retry_retrieval", "retry_generation", "optimize", "abort", "done"]
    rationale: str
    retrieval_hint: str | None = None
    generation_hint: str | None = None


class AgentState(TypedDict, total=False):
    # input
    task_id: str
    spec: str
    oracle_ref: str
    coupling_map_name: str | None
    max_depth_ratio: float  # threaded from TaskSpec — see graph.py's resource_check
    assertions_text: str | None  # US3 — raw text; planner parses it once (T090), not per iteration
    assertions: list[Assertion]  # US3 — parsed once at input time, never re-parsed per iteration
    n_qubits_correction: QubitCountCorrection | None  # T090 — set by planner, read by the report

    # working — overwritten each iteration
    requirements: list[Requirement]
    chunks: list[Chunk]
    code: str
    iteration: int

    # current attempt's results
    static: StaticResult | None
    semantic: SemanticResult | None
    resource: ResourceResult | None
    assertion_results: list[AssertionOutcome] | None  # US3 — one entry per declared assertion
    requirement_results: list[RequirementOutcome] | None  # T091 — one per CHECKABLE requirement
    decision: CriticDecision | None

    # accumulators
    error_history: Annotated[list[ErrorRecord], add]
    trace: Annotated[list[dict], add]

    # terminal
    status: Literal[
        "running",
        # "success" means SOMETHING REAL about functional correctness was
        # verified and passed — either a reference comparison (semantic_check,
        # the regression-suite path) or every user-declared assertion
        # (assertion_check, the product path). It does NOT mean "the pipeline
        # finished without errors": that is `completed_unverified` below.
        "success",
        # US4: the run completed with no pending error, but nothing verified
        # functional correctness — no oracle_ref AND no assertions (or
        # assertions that never resolved). Split out from "success" because
        # an invariant that depends on every consumer remembering to also
        # read `guarantee_report.functional_correctness_verified` is an
        # invariant that will be broken by the first thing that aggregates
        # `status` alone (a metrics table, a CI summary, analysis/metrics.py
        # when T059 lands). The type carries the distinction instead.
        "completed_unverified",
        "failed_semantic",
        "failed_static",
        "aborted",
        "infrastructure_error",
        "rejected_input",
        # US3: the SAME assertion came back not-evaluable on two consecutive
        # attempts — distinct from "aborted" (MAX_ITER exhaustion) and from
        # "failed_semantic" (a well-posed check that simply didn't pass).
        # Regenerating didn't help twice in a row, which is evidence the
        # assertion itself may not match what any correct circuit for this
        # task would produce — a user-declaration problem, not necessarily a
        # generation one. See validators/assertions.py and report.py (US4).
        "assertion_not_evaluable",
    ]
    # US4 — built once, by finalize (T096). Typed `Any`, not `GuaranteeReport
    # | None` (report.py, which the real type lives in): report.py imports
    # Assertion/AssertionOutcome/ResourceResult FROM this module, so a
    # module-level import in the other direction would be circular, and a
    # TYPE_CHECKING-guarded one breaks at runtime — LangGraph's
    # `StateGraph(AgentState)` calls `typing.get_type_hints()`, which tries
    # to eval every annotation's forward references against this module's
    # own namespace and fails on a name that was never actually imported at
    # runtime (confirmed: this exact setup raised `NameError: name
    # 'GuaranteeReport' is not defined` from inside `get_type_hints`,
    # before it was caught and reverted to `Any` here).
    guarantee_report: Any
