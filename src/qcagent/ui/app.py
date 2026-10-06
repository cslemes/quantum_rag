"""The interface (US6): submit, watch, read the guarantee (FR-022/023/024).

Scope is deliberately small (P2): in memory, single user, no auth, no
persistence, no export beyond copy. If a feature is not needed to show the
system working, it does not ship here.

Three endpoints and one page:

    GET  /              the page
    POST /api/validate  parse assertions ONLY — the same parser the planner uses
    GET  /api/run       the run, streamed as Server-Sent Events

The validate endpoint exists so the browser never grows a second, more
forgiving grammar. A front-end validator that accepts what the backend
refuses is how a user ends up caught in the gap between two parsers (F11), so
the browser asks this endpoint and this endpoint calls `parse_assertions`.
"""

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient

from qcagent.config import settings
from qcagent.live import LiveServices
from qcagent.llm.base import BaseLLMClient
from qcagent.llm.profiles import (
    Profile,
    ProfileError,
    ProfileStatus,
    build_client,
    get_profile,
    identity_stamps,
    load_profiles,
    probe,
    redact,
    reset_server_state,
)
from qcagent.retrieval.embedding import FastEmbedEmbedder
from qcagent.ui.session import check_service_health, check_stored_circuit, run_streaming
from qcagent.validators.assertions import AssertionParseError, parse_assertions, render_assertion
from qcagent.validators.sandbox import WorkerPool

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="qcircuit-agent", docs_url=None, redoc_url=None)

_shared: dict | None = None
_clients: dict[str, BaseLLMClient] = {}


def _shared_services() -> dict:
    """Retrieval, embedder and worker pool: built once, shared by EVERY profile.
    The WorkerPool exists so `import qiskit` is paid once rather than per run
    (D1b), and the embedder loads its model from the pinned offline cache.
    Only the generator client differs between profiles — there is one graph,
    one verification path."""
    global _shared
    if _shared is None:
        _shared = {
            "qdrant": QdrantClient(url=settings.qdrant_url),
            "embedder": FastEmbedEmbedder(),
            "pool": WorkerPool(
                size=settings.worker_pool_size, recycle_after=settings.worker_recycle_after
            ),
        }
    return _shared


def services(profile: Profile) -> LiveServices:
    """The shared services plus THIS profile's client, from the one
    construction path (`build_client`)."""
    if profile.name not in _clients:
        _clients[profile.name] = build_client(profile)
    return LiveServices(llm=_clients[profile.name], **_shared_services())


def _public(profile: Profile, status: ProfileStatus, *, default: str) -> dict:
    """What the browser may see about a profile: names, states and reasons.
    Never a URL, a credential or an environment-variable value — the browser
    names a profile and nothing else."""
    return {
        "name": profile.name,
        "label": profile.label,
        "client_type": profile.client_type,
        "model": profile.model,
        "default": profile.name == default,
        "state": status.state,
        "reason": redact(status.reason, profile) if status.reason else None,
        "server_version": status.server_version,
        "expected_server_version": status.expected_server_version,
        "version_gate": status.version_gate,
        "usable": status.usable,
        "checked_at": status.checked_at,
    }


class ValidateRequest(BaseModel):
    assertions_text: str
    n_qubits: int


class CheckRequest(BaseModel):
    """Which circuit, named explicitly. Not "the last run" — that changes
    silently under a second tab, and the one thing a verdict must never be
    is ambiguous about what it is a verdict ABOUT."""

    token: str
    assertions_text: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/profiles")
def profiles() -> dict:
    """Every profile, probed LIVE on each call. Reachability is never cached at
    startup: the natural order is app, then pod, then tunnel, so a boot-time
    read would show a false 'unreachable' for a backend that is up now."""
    loaded = load_profiles()
    with ThreadPoolExecutor(max_workers=max(1, len(loaded.profiles))) as pool:
        statuses = list(pool.map(probe, loaded.profiles))
    return {
        "default": loaded.default,
        "profiles": [
            _public(p, st, default=loaded.default)
            for p, st in zip(loaded.profiles, statuses, strict=True)
        ],
    }


@app.get("/api/profiles/{name}/status")
def profile_status(name: str) -> dict:
    """One profile, probed live — on selection and on an explicit refresh."""
    try:
        profile = get_profile(name)
    except ProfileError:
        raise HTTPException(status_code=404, detail="unknown generator profile") from None
    return _public(profile, probe(profile), default=load_profiles().default)


@app.get("/api/health")
def health() -> dict:
    return check_service_health()


@app.post("/api/validate")
def validate(request: ValidateRequest) -> dict:
    """Parses assertions and returns either the system's READING of each one
    or the first error.

    Echoing the parse back through `render_assertion` — the parser's own
    inverse — is the point: it shows what was understood rather than what was
    typed. A user who wrote `|01>` meaning something else sees it here, and
    the ket convention is where the cold-validation exercise showed people go
    wrong even when they know the grammar.
    """
    text = request.assertions_text.strip()
    if not text:
        return {"ok": True, "assertions": []}
    try:
        parsed = parse_assertions(text, request.n_qubits)
    except AssertionParseError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "assertions": [render_assertion(a) for a in parsed]}


@app.post("/api/check")
def check(request: CheckRequest) -> dict:
    """Evaluate assertions against a circuit that ALREADY EXISTS — no LLM, no
    generation.

    This separates two operations the interface had merged: "does this
    circuit satisfy X?" and "generate a circuit satisfying X". Declaring an
    assertion drafted from an observed distribution used to trigger the
    second when the user meant the first, and since the generator is
    unreliable the new circuit routinely violated assertions drafted from the
    old one.

    A check that passes IS functional verification of that circuit with
    respect to those assertions, so the report may legitimately say VERIFIED.
    """
    return check_stored_circuit(request.token, request.assertions_text)


@app.get("/api/run")
def run(spec: str, profile: str = "", assertions: str = "", max_iter: int = 5) -> StreamingResponse:
    """The run, streamed. `profile` is REQUIRED and names one generator.

    The profile is re-probed here, immediately before generating, whatever the
    page last showed. If it cannot be served the request is REFUSED with a
    `refused` event naming the profile and the reason. There is no fallback to
    another profile, silent or otherwise: the guarantee report would describe
    a run served by a generator it does not name.
    """

    def refused(message: str, **extra: str | None) -> Iterator[str]:
        yield f"event: refused\ndata: {json.dumps({'message': message, **extra})}\n\n"

    def stream() -> Iterator[str]:
        try:
            chosen = get_profile(profile)
        except ProfileError:
            names = [p.name for p in load_profiles().profiles]
            yield from refused(
                f"No generator profile named {profile[:64]!r} (choose one of {names}). "
                "Nothing was generated.",
                profile=None,
            )
            return
        status = probe(chosen)  # live, now — not what the page showed earlier
        if (message := status.refusal()) is not None:
            yield from refused(
                redact(message, chosen),
                profile=chosen.name,
                state=status.state,
                checked_at=status.checked_at,
            )
            return
        identity = identity_stamps(chosen, status)
        reset_server_state(chosen)  # the profile's determinism: reset before the run
        for event in run_streaming(
            services(chosen),
            spec=spec,
            assertions_text=assertions or None,
            max_iter=max_iter,
            generator=identity,
        ):
            yield f"event: {event.kind}\ndata: {json.dumps(event.data)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
