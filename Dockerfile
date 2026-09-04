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

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --group dev

COPY . .
RUN uv sync --frozen --group dev

ENV PATH="/opt/venv/bin:${PATH}"

CMD ["python", "-m", "qcagent"]
