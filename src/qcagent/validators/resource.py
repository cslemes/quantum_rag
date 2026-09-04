"""Resource verification — layer 4 (depth, CX count, width after
transpilation).

See contracts/validators.md.
"""

from qiskit import QuantumCircuit
from qiskit.compiler import transpile
from qiskit.transpiler import CouplingMap

from qcagent.state import ResourceResult

COUPLING_MAPS: dict[str, CouplingMap | None] = {
    "linear_5": CouplingMap.from_line(5),
    "all_to_all": None,
    # "heavy_hex_27" intentionally omitted: IBM's real 27-qubit devices
    # (e.g. ibmq_kolkata) use a fixed, hardware-specific edge list, not the
    # generic heavy-hex lattice formula — CouplingMap.from_heavy_hex(3)
    # produces 19 qubits, not 27, and no integer distance produces exactly
    # 27 for this construction. Add the real edge list here (sourced from
    # an actual backend, not fabricated) when T047's t4_hardware tasks need
    # it.
}


def check_resources(
    generated: QuantumCircuit,
    reference: QuantumCircuit,
    coupling_map_name: str,
    opt_level: int = 2,
    seed: int = 42,
    max_depth_ratio: float = 2.0,
) -> ResourceResult:
    """TRAP 3 — asymmetric transpilation. Transpile BOTH with IDENTICAL
    parameters (same opt_level, same coupling_map, same seed_transpiler).
    Comparing a transpiled circuit against an untranspiled reference is a
    methodological error and would produce a meaningless depth_ratio
    (FR-006).

    seed_transpiler is mandatory: routing passes are stochastic, and
    without a seed depth_ratio varies between runs of the same input.

    depth_ratio > max_depth_ratio -> passed=False, error_type="ResourceExcess"
    -> critic emits action="optimize".
    """
    coupling_map = COUPLING_MAPS[coupling_map_name]

    generated_t = transpile(
        generated,
        coupling_map=coupling_map,
        optimization_level=opt_level,
        seed_transpiler=seed,
    )
    reference_t = transpile(
        reference,
        coupling_map=coupling_map,
        optimization_level=opt_level,
        seed_transpiler=seed,
    )

    depth = generated_t.depth()
    cx_count = generated_t.count_ops().get("cx", 0)
    width = generated_t.num_qubits

    reference_depth = reference_t.depth()
    reference_cx_count = reference_t.count_ops().get("cx", 0)

    depth_ratio = depth / reference_depth if reference_depth > 0 else float("inf")
    cx_ratio = cx_count / reference_cx_count if reference_cx_count > 0 else float("inf")

    return ResourceResult(
        depth=depth,
        cx_count=cx_count,
        width=width,
        depth_ratio=depth_ratio,
        cx_ratio=cx_ratio,
        passed=depth_ratio <= max_depth_ratio,
    )
