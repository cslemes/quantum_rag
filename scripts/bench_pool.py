"""WorkerPool throughput check — empirical evidence for D1b (research.md).

D1b's claim: `import qiskit` costs ~1-2s, and a pool of pre-warmed workers
pays that cost ONCE per worker (at startup) instead of once per submitted
circuit. At D1b's ~27,000-call experimental matrix, 1.5s/call paid on every
call instead of amortized once is ~11h against a 72h wall-clock budget —
this script is the check that the pool actually delivers the amortization
the budget assumes, not just the design rationale for it.

Uses a SINGLE worker (`--pool-size 1`, the default) on purpose: the question
is binary — "is the import cost paid once or every time" — and a
multi-worker pool muddies that signal, since several workers finish their
own (parallel, background) import while an earlier submit is still blocking
on a different worker's queue. One worker means submit #1 is unambiguously
"first contact with this worker" and every submit after it is unambiguously
"reused" — exactly the two cases the interpretation below distinguishes.

Run inside the app container — Linux `fork`-based `multiprocessing`, the
same start method the experimental matrix actually runs under (research.md
D15). A Windows-native run would exercise `spawn` instead, which re-executes
the interpreter per process and would not test the same code path:

    docker compose exec app python scripts/bench_pool.py
"""

import argparse
import statistics

from qcagent.validators.sandbox import WorkerPool

VALID_CODE = """
from qiskit import QuantumCircuit
qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
"""

# research.md D1b: ~5,400 base task executions, up to ~5 retries each ->
# ~27,000 calls, against a 72h wall-clock target for the full matrix.
MATRIX_CALLS = 27_000
MATRIX_BUDGET_H = 72

# Below this, submit #1's extra overhead is noise, not evidence of
# amortization — `import qiskit` alone is documented at 1-2s (D1b), so
# anything under half a second of delta isn't that.
AMORTIZATION_THRESHOLD_S = 0.5


def run(n_submits: int, pool_size: int, recycle_after: int) -> list[tuple[float, float]]:
    """Submits `VALID_CODE` `n_submits` times, sequentially. Returns one
    (wall_time_s, exec_time_s) pair per submit, in order."""
    results: list[tuple[float, float]] = []
    with WorkerPool(size=pool_size, recycle_after=recycle_after) as pool:
        for _ in range(n_submits):
            result = pool.submit(VALID_CODE, timeout=30)
            if not result.ok:
                raise RuntimeError(f"submit failed unexpectedly: {result.stderr}")
            results.append((result.wall_time_s, result.exec_time_s))
    return results


def _print_table(results: list[tuple[float, float]]) -> None:
    print(f"{'submit':>6}  {'wall_time_s':>12}  {'exec_time_s':>12}  {'overhead_s':>11}")
    for i, (wall, exec_t) in enumerate(results, start=1):
        print(f"{i:>6}  {wall:>12.4f}  {exec_t:>12.4f}  {wall - exec_t:>11.4f}")


def interpret(results: list[tuple[float, float]]) -> str:
    """Builds the interpretation text. A plain function (not folded into
    `main`) so it's independently testable against synthetic data — see
    tests/unit/test_bench_pool.py."""
    first_wall, first_exec = results[0]
    rest = results[1:]
    mean_wall_rest = statistics.mean(w for w, _ in rest)
    mean_exec_rest = statistics.mean(e for _, e in rest)
    first_overhead = first_wall - first_exec
    rest_overhead_mean = mean_wall_rest - mean_exec_rest
    delta = first_overhead - rest_overhead_mean

    lines = [
        f"submit #1:             wall={first_wall:.4f}s  exec={first_exec:.4f}s  "
        f"overhead={first_overhead:.4f}s",
        f"submits #2-{len(results)} (mean): wall={mean_wall_rest:.4f}s  "
        f"exec={mean_exec_rest:.4f}s  overhead={rest_overhead_mean:.4f}s",
        "",
    ]

    if delta >= AMORTIZATION_THRESHOLD_S:
        saved_per_call_h = (MATRIX_CALLS * delta) / 3600
        lines.append(
            f"Submit #1 cost {delta:.4f}s more overhead than the mean of the rest "
            f"— consistent with D1b: the pool amortizes the `import qiskit` cost "
            f"once, at worker startup, not on every submit."
        )
        lines.append(
            f"Extrapolated to D1b's ~{MATRIX_CALLS:,}-call matrix: paying "
            f"{delta:.2f}s on every call instead of once would cost "
            f"~{saved_per_call_h:.1f}h of wall-clock against the "
            f"{MATRIX_BUDGET_H}h target — this is exactly the cost the pool "
            f"design is meant to avoid, and this run confirms it does."
        )
    else:
        lines.append(
            f"WARNING: submit #1 did NOT cost meaningfully more than the "
            f"steady-state mean (delta={delta:.4f}s, threshold="
            f"{AMORTIZATION_THRESHOLD_S}s). Every submit is paying roughly the "
            f"same overhead."
        )
        lines.append(
            "This means the worker is very likely being recreated per call "
            "rather than reused — the pool is providing NO amortization "
            "benefit, contrary to D1b's design assumption. Do not trust "
            "latency numbers gathered under this configuration; investigate "
            "WorkerPool before running anything on the experimental matrix."
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submits", type=int, default=20)
    parser.add_argument("--pool-size", type=int, default=1)
    parser.add_argument("--recycle-after", type=int, default=100)
    args = parser.parse_args()

    results = run(args.submits, args.pool_size, args.recycle_after)
    _print_table(results)
    print()
    print("-- interpretation " + "-" * 50)
    print(interpret(results))


if __name__ == "__main__":
    main()
