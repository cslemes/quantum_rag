"""The sandbox worker: one fresh interpreter, one request per line.

Run as `python -m qcagent.validators.sandbox_worker`. Reads one JSON object per
line on stdin ({"code": ...}) and answers one JSON line on a dup of the original
stdout (anything else that reaches fd 1, a C extension's print, goes to stderr so
it cannot corrupt the protocol). Exits when stdin closes, which is also what
happens if the orchestrator dies. See `sandbox.py` for why this is a fresh
interpreter and not a fork.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    protocol = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
    os.dup2(2, 1)

    import qiskit  # noqa: F401  # import cost paid once per worker, not per task
    from qiskit import qpy  # noqa: F401  # exercised inside the exec'd wrapper

    # The one place generated code is executed is sandbox.py (a contract test
    # pins that); this module only carries requests to it and answers back.
    from qcagent.validators.sandbox import execute_generated

    protocol.write(json.dumps({"ready": True}) + "\n")  # imports done: now warm
    for line in sys.stdin:
        protocol.write(json.dumps(execute_generated(json.loads(line)["code"])) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
