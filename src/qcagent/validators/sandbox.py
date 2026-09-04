"""Isolated execution of generated code (FR-025). See contracts/validators.md.

A `WorkerPool` of pre-warmed subprocesses (qiskit already imported) replaces
spawning a fresh subprocess per execution — see research.md D1b: with
~27,000 calls across the experimental matrix, `import qiskit` alone
(1-2s) would cost 8-15h if paid on every call.

Isolation (FR-025) is preserved: each worker is still a process separate
from the orchestrator. What changes is that it's reused instead of
recreated. A worker that hits its timeout is killed and replaced, never
reused — it may have left a thread dangling.
"""

import multiprocessing as mp
import queue
import time
from pathlib import Path

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


def _worker_main(task_queue: mp.Queue, result_queue: mp.Queue) -> None:
    """Runs in a pre-warmed subprocess for its whole lifetime. Imports
    qiskit once here (the expensive part, D1b), then loops on tasks until
    it receives the poison pill (`None`)."""
    import contextlib
    import io
    import tempfile

    import qiskit  # noqa: F401  # import cost paid once per worker, not per task
    from qiskit import qpy  # noqa: F401  # exercised inside the exec'd wrapper

    while True:
        code = task_queue.get()
        if code is None:  # poison pill — shut down
            return

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
        except Exception as exc:  # noqa: BLE001 — reported to caller, not raised
            stderr.write(f"{type(exc).__name__}: {exc}\n")
        finally:
            Path(artifact_path).unlink(missing_ok=True)

        exec_time_s = time.perf_counter() - start
        result_queue.put(
            SandboxResult(
                ok=ok,
                circuit_qpy=circuit_bytes,
                stdout=stdout.getvalue(),
                stderr=stderr.getvalue(),
                wall_time_s=exec_time_s,  # overwritten by the pool with true wall time
                exec_time_s=exec_time_s,
            ).model_dump()
        )


class _Worker:
    def __init__(self) -> None:
        self.task_q: mp.Queue = mp.Queue()
        self.result_q: mp.Queue = mp.Queue()
        self.proc = mp.Process(target=_worker_main, args=(self.task_q, self.result_q), daemon=True)
        self.proc.start()
        self.uses = 0

    def stop(self) -> None:
        try:
            self.task_q.put_nowait(None)
        except Exception:  # noqa: BLE001 — best-effort; terminate covers it
            pass
        self.proc.join(timeout=2)
        if self.proc.is_alive():
            self.proc.terminate()
            self.proc.join(timeout=2)
        if self.proc.is_alive():
            self.proc.kill()


class WorkerPool:
    """Pool of pre-warmed processes. See module docstring and D1b."""

    def __init__(self, size: int = 6, recycle_after: int = 50) -> None:
        self.size = size
        self.recycle_after = recycle_after
        self._workers = [_Worker() for _ in range(size)]
        self._next = 0

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
        worker.task_q.put(code)
        try:
            raw = worker.result_q.get(timeout=timeout)
        except queue.Empty:
            worker.stop()
            self._workers[slot] = _Worker()
            return SandboxResult(
                ok=False,
                circuit_qpy=None,
                stdout="",
                stderr=f"timeout after {timeout}s",
                wall_time_s=time.perf_counter() - wall_start,
                exec_time_s=time.perf_counter() - wall_start,
            )

        result = SandboxResult.model_validate(raw)
        result.wall_time_s = time.perf_counter() - wall_start

        worker.uses += 1
        if worker.uses >= self.recycle_after:
            worker.stop()
            self._workers[slot] = _Worker()

        return result

    def shutdown(self) -> None:
        for worker in self._workers:
            worker.stop()

    def __enter__(self) -> "WorkerPool":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.shutdown()
