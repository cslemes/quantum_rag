import pytest

from qcagent.validators.sandbox import WorkerPool

VALID_CODE = """
from qiskit import QuantumCircuit
qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
"""


@pytest.fixture(scope="module")
def pool():
    with WorkerPool(size=2, recycle_after=100) as p:
        yield p


def test_valid_code_produces_qpy(pool: WorkerPool) -> None:
    result = pool.submit(VALID_CODE, timeout=10)
    assert result.ok
    assert result.circuit_qpy is not None
    assert len(result.circuit_qpy) > 0
    assert result.stderr == ""


def test_missing_qc_variable_fails_cleanly(pool: WorkerPool) -> None:
    result = pool.submit("x = 1", timeout=10)
    assert not result.ok
    assert result.circuit_qpy is None
    assert "codigo nao definiu variavel" in result.stderr


def test_denylist_blocks_before_invoking_worker(pool: WorkerPool) -> None:
    result = pool.submit("import os\nos.system('echo pwned')", timeout=10)
    assert not result.ok
    assert "denylist" in result.stderr
    assert result.wall_time_s == 0.0
    assert result.exec_time_s == 0.0


@pytest.mark.parametrize(
    "forbidden_code",
    [
        "import subprocess",
        "import socket",
        "import sys",
        "__import__('os')",
        "eval('1')",
        "exec('1')",
        "open('/etc/passwd')",
        "Path('/etc/passwd')",
    ],
)
def test_denylist_covers_all_forbidden_tokens(pool: WorkerPool, forbidden_code: str) -> None:
    result = pool.submit(forbidden_code, timeout=10)
    assert not result.ok
    assert "denylist" in result.stderr


def test_timeout_kills_and_replaces_worker(pool: WorkerPool) -> None:
    result = pool.submit("import time\ntime.sleep(30)\nqc = None", timeout=1)
    assert not result.ok
    assert "timeout" in result.stderr

    # the pool must still be usable afterwards — the hung worker was
    # replaced, not left dangling in the round-robin rotation.
    follow_up = pool.submit(VALID_CODE, timeout=10)
    assert follow_up.ok


def test_worker_recycled_after_n_executions_does_not_leak_state() -> None:
    with WorkerPool(size=1, recycle_after=2) as p:
        first = p.submit(VALID_CODE, timeout=10)
        assert first.ok
        original_pid = p._workers[0].proc.pid

        p.submit(VALID_CODE, timeout=10)  # uses == recycle_after -> recycled
        assert p._workers[0].proc.pid != original_pid

        third = p.submit(VALID_CODE, timeout=10)
        assert third.ok


# -- workers are fresh interpreters, not forks of the orchestrator -------------
#
# Once the orchestrator has used qiskit's Rust thread pool (SparsePauliOp.to_matrix,
# Operator(SparsePauliOp)), a worker FORKED from it hangs on the same call in
# generated code until the timeout. Creating the pool first protected only the
# workers that existed at that moment; a worker replaced later was forked from the
# poisoned parent. These tests poison the orchestrator and then exercise every path
# that creates a worker.

TO_MATRIX_CODE = """
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp
SparsePauliOp(["ZZ", "XI"], coeffs=[1.0, 0.5]).to_matrix()
qc = QuantumCircuit(2)
"""


def _poison_the_orchestrator() -> None:
    from qiskit.quantum_info import SparsePauliOp

    SparsePauliOp(["ZZ", "XI"], coeffs=[1.0, 0.5]).to_matrix()


def test_workers_created_after_the_orchestrator_used_the_rust_pool_still_run_to_matrix() -> None:
    _poison_the_orchestrator()
    with WorkerPool(size=2, recycle_after=100) as p:
        assert p.submit(TO_MATRIX_CODE, timeout=20).ok


def test_a_worker_replaced_after_use_count_runs_to_matrix_after_the_parent_was_poisoned() -> None:
    with WorkerPool(size=1, recycle_after=1) as p:  # pool FIRST, as the first fix had it
        _poison_the_orchestrator()  # ... and the parent is poisoned only afterwards
        for _ in range(3):  # use 1 = the initial worker, uses 2 and 3 = replacements
            assert p.submit(TO_MATRIX_CODE, timeout=20).ok


def test_a_worker_replaced_after_a_timeout_runs_to_matrix_after_the_parent_was_poisoned() -> None:
    with WorkerPool(size=1, recycle_after=100) as p:
        _poison_the_orchestrator()
        hung = p.submit("import time\ntime.sleep(30)\nqc = None", timeout=1)
        assert not hung.ok and "timeout" in hung.stderr
        assert p.submit(TO_MATRIX_CODE, timeout=20).ok  # the replacement worker


def test_a_worker_that_dies_is_reported_and_replaced() -> None:
    with WorkerPool(size=1, recycle_after=100) as p:
        p._workers[0].proc.kill()
        p._workers[0].proc.wait()
        died = p.submit(VALID_CODE, timeout=10)
        assert not died.ok and "worker died" in died.stderr
        assert p.submit(VALID_CODE, timeout=10).ok


def test_a_worker_exits_when_its_orchestrator_closes_the_pipe() -> None:
    with WorkerPool(size=1, recycle_after=100) as p:
        proc = p._workers[0].proc
        assert p.submit(VALID_CODE, timeout=10).ok
    assert proc.poll() is not None  # shutdown ended the worker; nothing is left behind
