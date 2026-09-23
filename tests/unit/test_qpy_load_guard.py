"""A circuit that cannot cross our own serialization boundary (bug 21).

The sandbox builds a circuit in a subprocess and hands it back as QPY. On one
QAOA task, Qiskit's own reader refused bytes Qiskit had just written —
`IndexError: list assignment index out of range` from `read_circuit`'s
register reconstruction. Unguarded, it escaped the graph and cost a run.

The trigger is NOT reproduced: a dozen register- and ParameterVector-shaped
circuits round-trip fine. So this is containment plus evidence, not an
explanation. What it buys is that the next occurrence is diagnosable — the
run terminates normally, so `final_code` is recorded, where a harness error
recorded no code at all.
"""

import io

from qiskit import QuantumCircuit, qpy

from qcagent.state import ERROR_TAXONOMY
from qcagent.validators.sandbox import SandboxResult
from qcagent.validators.static import check_static


def _sandbox_ok(circuit_qpy: bytes) -> SandboxResult:
    return SandboxResult(
        ok=True, circuit_qpy=circuit_qpy, stdout="", stderr="", wall_time_s=0.1, exec_time_s=0.1
    )


class _PoolReturning:
    def __init__(self, result: SandboxResult) -> None:
        self._result = result

    def submit(self, code: str) -> SandboxResult:
        return self._result


def _valid_qpy() -> bytes:
    qc = QuantumCircuit(2)
    qc.h(0)
    buf = io.BytesIO()
    qpy.dump(qc, buf)
    return buf.getvalue()


def test_unreadable_qpy_is_reported_not_raised() -> None:
    corrupt = bytearray(_valid_qpy())
    corrupt[20:40] = b"\x00" * 20  # valid header, broken body

    result = check_static(
        "qc = None",
        None,
        _PoolReturning(_sandbox_ok(bytes(corrupt))),
    )

    assert result.error is not None
    assert result.error.error_type == "CircuitSerializationFailure"
    assert result.error.error_type in ERROR_TAXONOMY
    assert result.transpiled is False
    assert result.executed is True, "the code DID run; it is the transport that failed"


def test_the_failure_carries_a_fingerprint_for_the_next_occurrence() -> None:
    """Storing the QPY itself would break JSON serialization (bug 14), so the
    record carries what identifies the exact bytes instead."""
    corrupt = bytearray(_valid_qpy())
    corrupt[20:40] = b"\x00" * 20

    result = check_static(
        "qc = None",
        None,
        _PoolReturning(_sandbox_ok(bytes(corrupt))),
    )

    payload = result.error.payload
    assert len(payload["qpy_sha256_16"]) == 16
    assert payload["qpy_bytes"] == len(corrupt)
    assert payload["qiskit_version"]


def test_a_readable_circuit_is_unaffected() -> None:
    result = check_static(
        "qc = None",
        None,
        _PoolReturning(_sandbox_ok(_valid_qpy())),
    )

    assert result.error is None
    assert result.transpiled is True


def test_the_record_is_json_safe() -> None:
    """The payload must survive `model_dump(mode="json")` — the exact thing
    that killed a suite in bug 14."""
    import json

    corrupt = bytearray(_valid_qpy())
    corrupt[20:40] = b"\x00" * 20
    result = check_static(
        "qc = None",
        None,
        _PoolReturning(_sandbox_ok(bytes(corrupt))),
    )

    json.dumps(result.error.model_dump(mode="json"))  # must not raise
