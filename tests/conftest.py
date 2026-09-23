"""Suite-wide guarantees (research.md D18b).

1. The test suite never reaches the network. Any attempt to open a
   non-loopback TCP/UDP connection fails immediately with
   `NetworkAccessInTests`, naming the destination. Before this, the
   integration tests constructed fastembed models that contacted HuggingFace
   Hub on every construction, even fully cached; when the network hiccuped,
   fastembed slept through its retries and one run took 99 s and produced
   errors nobody could name. A suite that fails for reasons outside the code
   trains people to ignore failures. Models now load from the pinned cache
   (`make models`), and this guard makes a new network dependency fail loudly
   at the line that introduced it instead of intermittently later.

2. A failure is always identifiable afterwards. Every session with a failure
   or error appends the failing test ids, the git revision and the session
   duration to `.pytest_cache/failures.log`. Pytest's own short summary
   (`-ra`) already names them, but terminal output gets truncated, piped
   through `tail`, or scrolled away — which is exactly how the one
   unexplained failure in this project lost its name.
"""

import ipaddress
import os
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Belt and braces for (1): huggingface_hub then refuses network calls itself.
os.environ.setdefault("HF_HUB_OFFLINE", "1")


class NetworkAccessInTests(RuntimeError):
    """A test tried to reach the network. Deliberately NOT an OSError, so
    library code that retries on connection errors (fastembed,
    huggingface_hub, requests) cannot swallow it and sleep."""


def _is_loopback(address: object) -> bool:
    if not isinstance(address, tuple):
        return True  # AF_UNIX path — local by definition
    host = address[0]
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # any other hostname means a lookup and a remote peer


def _guard(real):
    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address):
            raise NetworkAccessInTests(
                f"a test tried to connect to {address!r}. The suite must not depend on "
                "the network: pin the data locally (models: `make models`) or mock the "
                "call. See tests/conftest.py and research.md D18b."
            )
        return real(self, address)

    return connect


socket.socket.connect = _guard(socket.socket.connect)  # type: ignore[method-assign]
socket.socket.connect_ex = _guard(socket.socket.connect_ex)  # type: ignore[method-assign]


# -- (2) durable failure record --------------------------------------------------

_FAILURES_LOG = Path(__file__).resolve().parents[1] / ".pytest_cache" / "failures.log"
_failures: list[str] = []
_session_start = time.monotonic()


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.failed:
        outcome = "FAILED" if report.when == "call" else f"ERROR at {report.when}"
        first_line = str(report.longrepr).strip().splitlines()[-1] if report.longrepr else ""
        _failures.append(f"  {outcome} {report.nodeid} — {first_line[:200]}")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not _failures:
        return
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        revision = "unknown"
    _FAILURES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _FAILURES_LOG.open("a") as log:
        log.write(
            f"{datetime.now(UTC).isoformat(timespec='seconds')} git={revision or 'unknown'} "
            f"duration={time.monotonic() - _session_start:.1f}s failures={len(_failures)}\n"
        )
        log.write("\n".join(_failures) + "\n")


def pytest_terminal_summary(terminalreporter) -> None:
    if _failures:
        terminalreporter.write_line(
            f"{len(_failures)} failing test id(s) recorded in {_FAILURES_LOG}", red=True
        )


# ---------------------------------------------------------------------------
# The live retrieval index is not the tests' to damage
# ---------------------------------------------------------------------------
#
# `tests/unit/test_index.py` needs a REAL Qdrant (`:memory:` mode silently
# skips payload indexes), and for a long time it created, recreated and
# deleted the PRODUCTION collection to get one. Every `pytest` run therefore
# destroyed the ingested corpus, and the next `make eval` measured a
# generator with no retrieval — reported under the name of the system that
# has retrieval. It went unnoticed because nothing connects a green test run
# to a later empty index.
#
# Those tests now use a throwaway collection. This guard is here because
# fixing the one test that did it does not stop the next one: it records the
# real collection's point count at session start and fails LOUDLY at the end
# if it changed. A convention ("don't touch qdocs") is exactly the kind of
# invariant that depends on everyone remembering; this one notices.

_QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
_index_points_at_start: int | None = None


def _live_index_points() -> int | None:
    """Point count of the production collection, or None when there is no
    server or no collection — both are legitimate states to run tests in."""
    try:
        import httpx

        response = httpx.get(f"{_QDRANT_URL}/collections/qdocs", timeout=1.0)
        if response.status_code != 200:
            return None
        return int(response.json()["result"]["points_count"])
    except Exception:
        return None


def pytest_sessionstart(session: pytest.Session) -> None:
    global _index_points_at_start
    _index_points_at_start = _live_index_points()


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config: pytest.Config) -> None:
    before = _index_points_at_start
    if before is None:
        return
    after = _live_index_points()
    if after == before:
        return
    raise pytest.UsageError(
        f"A TEST DAMAGED THE LIVE RETRIEVAL INDEX: collection 'qdocs' held {before} points "
        f"before this session and {'is now gone' if after is None else f'holds {after}'} now. "
        "Tests must use a throwaway collection (see tests/unit/test_index.py::TEST_COLLECTION). "
        f"Re-run `make index` to restore it."
    )
