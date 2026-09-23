FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# CUDA 12.1 base — required for the optional qiskit-aer-gpu extra (D1) and to
# match the host RTX 3070 driver stack. The app runs Aer on CPU by default
# (GPU_THRESHOLD_QUBITS=18); this base only needs to be present for the [gpu]
# extra to build/run when explicitly enabled.

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

# research.md D18 — on a network that intercepts TLS (corporate proxy or
# antivirus doing SSL inspection), every HTTPS client in the image needs the
# intercepting CA in its trust store, or downloads (fastembed's HuggingFace
# pull, `pip`/`uv` if it ever hits the network, etc.) fail with a self-signed
# certificate error. NEVER work around this with verify=False / -k / an
# unverified SSL context — that disables verification for every request, not
# just the intercepted ones. To enable, on a machine that needs it:
#   1. Drop the corporate root CA (PEM format) at ./corporate-ca.crt in the
#      build context (gitignored — do not commit a real one).
#   2. Uncomment the two lines below.
#   3. Rebuild: `docker compose build app`.
# This installs the CA into the SYSTEM trust store (used by anything linking
# against OpenSSL directly), which is the right target for tools that ignore
# REQUESTS_CA_BUNDLE/SSL_CERT_FILE. The env-var route (set REQUESTS_CA_BUNDLE
# and SSL_CERT_FILE in .env — see .env.example and research.md D18) covers
# `requests`/`httpx`/`huggingface_hub` specifically and needs no rebuild; use
# it first, and reach for this block only if something in the image still
# fails to verify after that.
# The glob matches zero files when ./corporate-ca.crt is absent, so this is a
# no-op on a normal network and installs the CA automatically when the file is
# there — no commented-out block to remember to enable. Observed in practice:
# a Kaspersky "Personal Root Certificate" intercepting SOME connections to
# huggingface.co (research.md D18b), which is why downloads failed
# intermittently rather than always.
COPY corporate-ca.crt* /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Installing the CA in the system store covers everything that links against
# OpenSSL, but `requests` (and so `huggingface_hub`, and so the model
# download) verifies against certifi's own bundle unless pointed elsewhere —
# D18's two routes are complementary, not alternatives, and using only the
# system store is why the first image build still failed to verify. Both
# variables name the SYSTEM bundle, which `update-ca-certificates` above has
# already merged any corporate CA into, so this is correct on a normal
# network too. Never verify=False.
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --group dev

COPY . .
RUN uv sync --frozen --group dev

ENV PATH="/opt/venv/bin:${PATH}"

# research.md D18b — the embedding models are part of the image, at the exact
# revisions pinned in src/qcagent/retrieval/embedding.py. The network is
# needed at BUILD time only; every container runs with the models already on
# disk and loads them offline (`local_files_only=True`), so nothing in the
# canonical environment (D15) — ingestion, the agent, the test suite — depends
# on huggingface.co being reachable when it runs. This replaces D18's named
# volume, which made the download a first-run cost but still a runtime one.
# On a TLS-intercepting network, the build needs the CA block above.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
RUN python scripts/fetch_models.py /opt/fastembed

CMD ["python", "-m", "qcagent"]
