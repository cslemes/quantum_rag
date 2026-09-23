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
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient

from qcagent.config import settings
from qcagent.live import LiveServices
from qcagent.llm.ollama_client import OllamaClient
from qcagent.retrieval.embedding import FastEmbedEmbedder
from qcagent.ui.session import check_service_health, run_streaming
from qcagent.validators.assertions import AssertionParseError, parse_assertions, render_assertion
from qcagent.validators.sandbox import WorkerPool

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="qcircuit-agent", docs_url=None, redoc_url=None)

_services: LiveServices | None = None


def services() -> LiveServices:
    """Built once and shared. The WorkerPool exists so `import qiskit` is paid
    once rather than per run (D1b), and the embedder loads its model from the
    pinned offline cache."""
    global _services
    if _services is None:
        _services = LiveServices(
            llm=OllamaClient(
                settings.ollama_base_url,
                settings.ollama_model,
                settings.ollama_num_ctx,
                settings.ollama_temperature,
            ),
            qdrant=QdrantClient(url=settings.qdrant_url),
            embedder=FastEmbedEmbedder(),
            pool=WorkerPool(
                size=settings.worker_pool_size, recycle_after=settings.worker_recycle_after
            ),
        )
    return _services


class ValidateRequest(BaseModel):
    assertions_text: str
    n_qubits: int


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


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


@app.get("/api/run")
def run(spec: str, assertions: str = "", max_iter: int = 5) -> StreamingResponse:
    def stream() -> Iterator[str]:
        for event in run_streaming(
            services(),
            spec=spec,
            assertions_text=assertions or None,
            max_iter=max_iter,
        ):
            yield f"event: {event.kind}\ndata: {json.dumps(event.data)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
