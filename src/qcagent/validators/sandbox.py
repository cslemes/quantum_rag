"""Isolated execution of generated code (FR-025). See contracts/validators.md.

A `WorkerPool` of pre-warmed subprocesses (qiskit already imported) replaces
spawning a fresh subprocess per execution — see research.md D1b: with
~1,800 calls in a regression suite run's worst case (120 tasks x 3 seeds x
up to 5 retries — see MIGRATION.md, this replaced v1's 5,400-run/72h
experimental matrix), `import qiskit` alone (1-2s) would cost 30min-1h if
paid on every call, against SC-007's 3h budget for the whole suite.

Isolation (FR-025) is preserved: each worker is still a process separate
from the orchestrator. What changes is that it's reused instead of
recreated. A worker that hits its timeout is killed and replaced, never
reused — it may have left a thread dangling.

Workers are FRESH INTERPRETERS, started with `python -m
qcagent.validators.sandbox_worker`, never forks of the orchestrator. Found on
2026-10-24: once the orchestrator has used `Operator(SparsePauliOp)` or
`SparsePauliOp.to_matrix()` (qiskit's Rust thread pool), a worker FORKED from it
hangs on the same call in generated code until the 60 s timeout, and the cascade
labels that timeout `SyntaxError`. A fork taken at any time after that use is
affected, so creating the pool first only protects the workers that exist at
that moment, not the ones replaced later (after a timeout or `recycle_after`
uses). A fresh interpreter has no such state, whatever the orchestrator did.
"""

import base64
import json
import os
import select
import subprocess
import sys
import time

from pydantic import BaseModel

# Denylist runs BEFORE invoking a worker and produces ok=False without
# spending a worker slot on it.
FORBIDDEN = (
    "import os",
    "import subprocess",
    "import socket",
    "import sys",
    "__import__",
    "eval(",
    "exec(",
    "open(",
    "Path(",
)

_WRAPPER = """
{user_code}

from qiskit import qpy
if "qc" not in dir():
    raise RuntimeError("codigo nao definiu variavel `qc`")
with open({artifact!r}, "wb") as f:
    qpy.dump(qc, f)
"""


class SandboxResult(BaseModel):
    ok: bool
    circuit_qpy: bytes | None
    stdout: str
    stderr: str
    wall_time_s: float  # total time, including pool queue/IPC overhead
    exec_time_s: float  # time of the code itself, without pool overhead


def _check_denylist(code: str) -> str | None:
    for token in FORBIDDEN:
        if token in code:
            return token
    return None


def execute_generated(code: str) -> dict:
    """Run generated code in THIS process and describe the outcome as a JSON-able
    dict. Called only by `sandbox_worker`, in a worker's own interpreter; never by
    the orchestrator."""
    import contextlib
    import io
    import tempfile
    from pathlib import Path

    stdout, stderr = io.StringIO(), io.StringIO()
    start = time.perf_counter()
    ok = False
    circuit_bytes: bytes | None = None

    with tempfile.NamedTemporaryFile(suffix=".qpy", delete=False) as tmp:
        artifact_path = tmp.name
    wrapped = _WRAPPER.format(user_code=code, artifact=artifact_path)
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(compile(wrapped, "<generated>", "exec"), {})
        circuit_bytes = Path(artifact_path).read_bytes()
        ok = True
    except Exception as exc:  # noqa: BLE001 — reported to the caller, not raised
        stderr.write(f"{type(exc).__name__}: {exc}\n")
    finally:
        Path(artifact_path).unlink(missing_ok=True)

    return {
        "ok": ok,
        "circuit_qpy": (
            base64.b64encode(circuit_bytes).decode("ascii") if circuit_bytes is not None else None
        ),
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "exec_time_s": time.perf_counter() - start,
    }


class WorkerDied(RuntimeError):
    """The worker's pipe closed without an answer (it crashed or was killed)."""


class _Worker:
    """One fresh interpreter (`sandbox_worker`) behind a pair of pipes."""

    def __init__(self) -> None:
        env = dict(os.environ)
        # The worker must import the same `qcagent` the orchestrator did.
        env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "qcagent.validators.sandbox_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        self.uses = 0

    def _read_line(self, timeout: float) -> dict | None:
        assert self.proc.stdout is not None
        fd = self.proc.stdout.fileno()
        deadline = time.monotonic() + timeout
        buf = b""
        while b"\n" not in buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                return None
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                raise WorkerDied("worker closed its pipe")
            buf += chunk
        return json.loads(buf)

    def wait_ready(self, timeout: float = 120.0) -> None:
        """Block until the worker has imported qiskit. Workers used to be forked
        from an orchestrator that already had it imported, so they were warm on
        creation; a fresh interpreter has to be waited for, or the first task it
        serves is charged the import."""
        message = self._read_line(timeout)
        if message is None or not message.get("ready"):
            raise WorkerDied("worker did not become ready")

    def request(self, code: str, timeout: float) -> dict | None:
        """The worker's answer, or None if it did not answer within `timeout`.
        Raises `WorkerDied` if it exited without answering."""
        assert self.proc.stdin is not None and self.proc.stdout is not None
        try:
            self.proc.stdin.write(json.dumps({"code": code}).encode() + b"\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise WorkerDied(str(exc)) from exc
        return self._read_line(timeout)

    def stop(self) -> None:
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()  # EOF: the worker's loop ends
        except OSError:
            pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if self.proc.stdout is not None:
            self.proc.stdout.close()


class WorkerPool:
    """Pool of pre-warmed processes. See module docstring and D1b."""

    def __init__(self, size: int = 6, recycle_after: int = 50) -> None:
        self.size = size
        self.recycle_after = recycle_after
        self._workers = [_Worker() for _ in range(size)]
        for worker in self._workers:  # started together, so they warm up in parallel
            worker.wait_ready()
        self._next = 0

    @staticmethod
    def _fresh_worker() -> _Worker:
        worker = _Worker()
        worker.wait_ready()
        return worker

    def submit(self, code: str, timeout: int = 60) -> SandboxResult:
        """Executes `code` on the next worker (round-robin). Recycles the
        worker after `recycle_after` executions, to avoid state
        accumulating across tasks. A worker that times out is killed and
        replaced, never reused — it may have left a thread pending.
        """
        forbidden = _check_denylist(code)
        if forbidden is not None:
            return SandboxResult(
                ok=False,
                circuit_qpy=None,
                stdout="",
                stderr=f"denylist: forbidden token {forbidden!r}",
                wall_time_s=0.0,
                exec_time_s=0.0,
            )

        slot = self._next
        self._next = (self._next + 1) % self.size
        worker = self._workers[slot]

        wall_start = time.perf_counter()
        try:
            raw = worker.request(code, timeout)
            failure = f"timeout after {timeout}s" if raw is None else None
        except WorkerDied as exc:
            raw, failure = None, f"worker died: {exc}"
        if raw is None:
            worker.stop()
            self._workers[slot] = self._fresh_worker()
            return SandboxResult(
                ok=False,
                circuit_qpy=None,
                stdout="",
                stderr=failure or "no answer",
                wall_time_s=time.perf_counter() - wall_start,
                exec_time_s=time.perf_counter() - wall_start,
            )

        result = SandboxResult(
            ok=raw["ok"],
            circuit_qpy=(
                base64.b64decode(raw["circuit_qpy"]) if raw["circuit_qpy"] is not None else None
            ),
            stdout=raw["stdout"],
            stderr=raw["stderr"],
            wall_time_s=time.perf_counter() - wall_start,
            exec_time_s=raw["exec_time_s"],
        )

        worker.uses += 1
        if worker.uses >= self.recycle_after:
            worker.stop()
            self._workers[slot] = self._fresh_worker()

        return result

    def shutdown(self) -> None:
        for worker in self._workers:
            worker.stop()

    def __enter__(self) -> "WorkerPool":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.shutdown()
