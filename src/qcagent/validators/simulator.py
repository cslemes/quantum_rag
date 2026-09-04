"""Simulator backend selection. See contracts/validators.md and research.md D1."""

from qiskit_aer import AerSimulator

GPU_THRESHOLD_QUBITS = 18


def make_simulator(n_qubits: int, seed: int) -> AerSimulator:
    """CPU by default; GPU only above GPU_THRESHOLD_QUBITS (D1).

    Below ~18 qubits the GPU loses to the CPU (kernel launch overhead and
    host<->device transfer dominate), and it would compete for VRAM with
    Ollama during condition C5 with the local generator.

    max_parallel_experiments=1 is deliberate: parallelism lives in
    bench/runner.py. Letting Aer parallelize internally *and* the runner
    parallelize causes thread contention and makes per-execution latency
    non-reproducible, which contaminates the cost-per-execution metric.
    """
    return AerSimulator(
        method="statevector",
        device="GPU" if n_qubits >= GPU_THRESHOLD_QUBITS else "CPU",
        max_parallel_threads=8,  # 5700X: 8 physical cores
        max_parallel_experiments=1,
        seed_simulator=seed,  # required — Principle II (reproducibility)
    )
