"""Two runs are only comparable under the same controlled conditions.

The 0/360 divergence measured over two full runs is a property of the system
RUN THIS WAY — pinned temperature, fixed corpus, reset inference server,
explicit num_ctx. Comparing runs that disagree on any of those compares two
different systems, and the per-task diff reads as a regression that never
happened.

The gate refuses rather than trusting the operator to remember, for the same
reason F8/F10 gave: an invariant that depends on everyone remembering is one
that gets broken.
"""

import pytest

from analysis.compare import CONTROLLED_FIELDS, IncomparableRunsError, check_comparable
from bench.schema import RunRecord

GOOD = {
    "qiskit": "1.2.4",
    "ollama": "0.34.1",
    "hostname": "claude-Quantum-RAG",
    "python": "/home/agent/.venvs/qcagent/bin/python3",
    "platform": "Linux 7.0.12",
    "mp_start_method": "fork",
    "containerized": "no",
    "ollama_temperature": "0.0",
    "qdocs_points": "1019",
    "generator_state": "reset_before_run",
    "ollama_num_ctx": "16384",
}


def _record(**lib) -> RunRecord:
    return RunRecord(
        run_id="r",
        task_id="t",
        model_id="m",
        seed=1,
        status="success",
        iterations=1,
        final_code="qc = None",
        static=None,
        semantic=None,
        resource=None,
        guarantee_report=None,
        error_history=[],
        input_tokens=0,
        output_tokens=0,
        num_ctx=16384,
        cost_usd=0.0,
        latency_s=1.0,
        git_sha="abc",
        lib_versions={**GOOD, **lib},
        timestamp="2026-09-22T00:00:00+0000",
    )


def test_identical_conditions_compare_fine() -> None:
    check_comparable([_record()], [_record()])  # must not raise


@pytest.mark.parametrize("field", CONTROLLED_FIELDS)
def test_a_differing_controlled_field_refuses_the_comparison(field: str) -> None:
    with pytest.raises(IncomparableRunsError, match=field):
        check_comparable([_record()], [_record(**{field: "changed"})])


@pytest.mark.parametrize("field", CONTROLLED_FIELDS)
def test_a_missing_field_is_a_mismatch_not_a_pass(field: str) -> None:
    """A run recorded before the protocol existed cannot be shown to have met
    it. "Absent" must never read as "fine" — the same rule the tri-state
    verdicts follow everywhere else."""
    lib = {k: v for k, v in GOOD.items() if k != field}
    stale = RunRecord(
        run_id="old",
        task_id="t",
        model_id="m",
        seed=1,
        status="success",
        iterations=1,
        final_code="",
        static=None,
        semantic=None,
        resource=None,
        guarantee_report=None,
        error_history=[],
        input_tokens=0,
        output_tokens=0,
        num_ctx=None,
        cost_usd=0.0,
        latency_s=1.0,
        git_sha="abc",
        lib_versions=lib,
        timestamp="2026-09-19T00:00:00+0000",
    )
    with pytest.raises(IncomparableRunsError, match="predates the protocol"):
        check_comparable([stale], [_record()])


def test_the_refusal_says_how_to_fix_it() -> None:
    with pytest.raises(IncomparableRunsError) as excinfo:
        check_comparable([_record()], [_record(qdocs_points="1020")])
    message = str(excinfo.value)
    assert "1019" in message and "1020" in message, "name the actual values"
    assert "cold" in message, "say what protocol to re-run under"


def test_an_uncontrolled_field_does_not_block() -> None:
    """Only the fields that provably change the measurement gate it —
    otherwise every dependency bump would refuse every comparison."""
    check_comparable([_record()], [_record(qiskit="1.2.5")])


# --- the ollama binary: recorded since day one, verified only now -----------


def test_an_ollama_upgrade_refuses_the_comparison() -> None:
    """The gap `qdocs_points` used to have: recorded but unchecked. An upgrade
    changes generation output and surfaces only when someone reproduces the
    results later."""
    with pytest.raises(IncomparableRunsError, match="ollama"):
        check_comparable([_record(ollama="0.34.1")], [_record(ollama="0.35.0")])


# --- the GPU stack: declared, not detected ---------------------------------


def test_an_undeclared_gpu_stack_warns_rather_than_refusing(capsys) -> None:
    """A refusal on "unrecorded" would block every comparison ever run, and a
    gate that always fires teaches people to bypass it — the argument that
    retired the 5% threshold. The warning states the true claim: this axis was
    not verified."""
    check_comparable([_record()], [_record()])  # neither declares gpu_stack

    err = capsys.readouterr().err
    assert "gpu_stack" in err
    assert "NOT verified" in err
    assert "QCAGENT_GPU_STACK" in err, "say how to make it checkable"


def test_a_declared_and_differing_gpu_stack_is_a_hard_refusal() -> None:
    """Undeclared is unverified; declared-and-different is incomparable."""
    with pytest.raises(IncomparableRunsError, match="gpu_stack"):
        check_comparable(
            [_record(gpu_stack="driver=550.54,cuda=12.4")],
            [_record(gpu_stack="driver=560.35,cuda=12.6")],
        )


def test_a_declared_and_matching_gpu_stack_passes_silently(capsys) -> None:
    check_comparable(
        [_record(gpu_stack="driver=550.54,cuda=12.4")],
        [_record(gpu_stack="driver=550.54,cuda=12.4")],
    )
    assert "gpu_stack" not in capsys.readouterr().err


# --- where it ran (D15 amended, F21) ---------------------------------------


def test_a_different_environment_refuses_the_comparison() -> None:
    """Verification runs locally, so a different BLAS or CPU dispatch can flip
    `Operator.equiv()` at a tolerance boundary. Two runs from different
    environments are two systems, not one system measured twice."""
    with pytest.raises(IncomparableRunsError, match="containerized"):
        check_comparable([_record()], [_record(containerized="yes")])


def test_a_different_host_refuses_the_comparison() -> None:
    with pytest.raises(IncomparableRunsError, match="hostname"):
        check_comparable([_record()], [_record(hostname="other-machine")])


def test_a_different_interpreter_refuses_the_comparison() -> None:
    """The sandbox venv and the canonical image are both Linux+fork with
    identical package versions, and are still different builds."""
    with pytest.raises(IncomparableRunsError, match="python"):
        check_comparable([_record()], [_record(python="/opt/venv/bin/python")])


def test_a_spawn_run_never_compares_against_a_fork_run() -> None:
    """D15's substantive requirement: Linux + fork, never Windows spawn. It
    changes the WorkerPool's cost profile (D1b), so the two are incomparable
    even when every result matches."""
    with pytest.raises(IncomparableRunsError, match="mp_start_method"):
        check_comparable([_record()], [_record(mp_start_method="spawn")])
