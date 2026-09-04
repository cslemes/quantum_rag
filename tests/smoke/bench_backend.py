"""CPU vs GPU timing for AerSimulator, to empirically confirm
GPU_THRESHOLD_QUBITS (see research.md D1, T006b).

Not run by default (pytest.ini `addopts = -m 'not smoke'`). Run explicitly
on a machine with a working CUDA-capable qiskit-aer-gpu install:

    uv run pytest -m smoke tests/smoke/bench_backend.py -s

Adjust `GPU_THRESHOLD_QUBITS` in src/qcagent/validators/simulator.py with
whatever crossover this prints.
"""

import time

import pytest
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

QUBIT_COUNTS = (5, 10, 15, 18, 20)


def _ghz_circuit(n_qubits: int) -> QuantumCircuit:
    qc = QuantumCircuit(n_qubits)
    qc.h(0)
    for q in range(1, n_qubits):
        qc.cx(0, q)
    qc.measure_all()
    return qc


def _time_backend(device: str, n_qubits: int, shots: int = 100) -> float:
    sim = AerSimulator(method="statevector", device=device, seed_simulator=0)
    qc = _ghz_circuit(n_qubits)
    # warm-up run — excludes one-time backend/context initialization from the
    # measurement, same caution as D10's throughput benchmark.
    sim.run(qc, shots=1).result()
    start = time.perf_counter()
    sim.run(qc, shots=shots).result()
    return time.perf_counter() - start


def _gpu_available() -> bool:
    try:
        AerSimulator(method="statevector", device="GPU").run(_ghz_circuit(2), shots=1).result()
        return True
    except Exception:
        return False


@pytest.mark.smoke
def test_cpu_vs_gpu_crossover() -> None:
    if not _gpu_available():
        pytest.skip("no CUDA-capable qiskit-aer-gpu backend available in this environment")

    print(f"\n{'qubits':>6} | {'CPU (s)':>10} | {'GPU (s)':>10} | faster")
    print("-" * 45)
    crossover = None
    for n in QUBIT_COUNTS:
        cpu_t = _time_backend("CPU", n)
        gpu_t = _time_backend("GPU", n)
        faster = "GPU" if gpu_t < cpu_t else "CPU"
        if faster == "GPU" and crossover is None:
            crossover = n
        print(f"{n:>6} | {cpu_t:>10.4f} | {gpu_t:>10.4f} | {faster}")

    print(f"\nmeasured crossover (first n where GPU < CPU): {crossover}")
    print("update GPU_THRESHOLD_QUBITS in validators/simulator.py accordingly")


if __name__ == "__main__":
    test_cpu_vs_gpu_crossover()
