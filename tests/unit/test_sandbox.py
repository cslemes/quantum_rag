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
