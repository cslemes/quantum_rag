"""Static verification — layers 1-2 (executability, transpilability).

See contracts/validators.md and data-model.md's closed error taxonomy.
"""

import ast
import io

from qiskit import qpy
from qiskit.compiler import transpile
from qiskit.transpiler import CouplingMap

from qcagent.state import ErrorRecord, StaticResult
from qcagent.validators.sandbox import WorkerPool

DEPRECATED_SYMBOLS = {
    "execute": "Use backend.run() ou Sampler/Estimator (Qiskit 1.x)",
    "QuantumInstance": "Removido — use primitives",
    "qiskit.providers.aer": "Renomeado para qiskit_aer",
    "qiskit.opflow": "Removido — use quantum_info.SparsePauliOp",
    "qiskit.algorithms": "Movido para qiskit_algorithms",
    "assemble": "Removido no Qiskit 1.0",
}

# Exception type names the sandbox wrapper reports (as "{type(exc).__name__}:
# ...", see sandbox.py) that indicate the generator invented an API that
# never existed — distinct from a *renamed/removed* one already caught by
# DEPRECATED_SYMBOLS above. Both route to retry_retrieval per plan.md's
# critic table: "Símbolo obsoleto, ImportError, AttributeError ->
# retry_retrieval" groups them together, since both mean the model needs
# more API context, not a rewrite from scratch.
_HALLUCINATION_EXCEPTIONS = ("ImportError", "AttributeError", "ModuleNotFoundError", "NameError")


def _classify_sandbox_failure(stderr: str) -> str:
    """Maps a sandbox execution failure to the closed error taxonomy
    (data-model.md), grounded in plan.md's critic routing table.

    - ImportError/AttributeError/... -> HallucinatedSymbol.
    - A qubit-index CircuitError (e.g. "Index 5 out of range for size 2")
      -> QubitIndexError. Routes identically to SyntaxError in the critic
      table ("qubit fora de faixa" is grouped with syntax/transpilation
      failures under retry_generation), but kept distinct here for the
      qualitative failure taxonomy (T064).
    - Anything else falls back to SyntaxError. This isn't an invented
      catch-all: the contract's own worked example (code that never
      defines `qc`) is itself a RuntimeError classified as SyntaxError, so
      "the sandbox rejected this code" already maps to SyntaxError by the
      contract's own convention.
    """
    if stderr.startswith(_HALLUCINATION_EXCEPTIONS):
        return "HallucinatedSymbol"
    if "CircuitError" in stderr and "out of range" in stderr:
        return "QubitIndexError"
    return "SyntaxError"


def check_static(code: str, coupling_map: CouplingMap | None, pool: WorkerPool) -> StaticResult:
    """Sequential gates:
      1. DEPRECATED_SYMBOLS scan  -> error_type="DeprecatedAPI"
      2. ast.parse                -> error_type="SyntaxError"
      3. pool.submit               -> produces QPY
      4. transpile(coupling_map)  -> error_type="TranspilationFailure"

    The scan runs BEFORE execution and is what distinguishes H1 from H2:
    `DeprecatedAPI` is the only category the critic routes to
    `retry_retrieval`. Without this separation, the hypothesis about the
    value of retrieval isn't testable.
    """
    for symbol, replacement in DEPRECATED_SYMBOLS.items():
        if symbol in code:
            return StaticResult(
                parsed=False,
                executed=False,
                transpiled=False,
                error=ErrorRecord(
                    iteration=0,
                    stage="static",
                    error_type="DeprecatedAPI",
                    message=f"uso de símbolo obsoleto {symbol!r}: {replacement}",
                ),
            )

    try:
        ast.parse(code)
    except SyntaxError as exc:
        return StaticResult(
            parsed=False,
            executed=False,
            transpiled=False,
            error=ErrorRecord(
                iteration=0, stage="static", error_type="SyntaxError", message=str(exc)
            ),
        )

    sandbox_result = pool.submit(code)
    if not sandbox_result.ok:
        return StaticResult(
            parsed=True,
            executed=False,
            transpiled=False,
            error=ErrorRecord(
                iteration=0,
                stage="static",
                error_type=_classify_sandbox_failure(sandbox_result.stderr),
                message=sandbox_result.stderr.strip(),
            ),
        )

    assert sandbox_result.circuit_qpy is not None  # ok=True guarantees this
    with io.BytesIO(sandbox_result.circuit_qpy) as buf:
        (qc,) = qpy.load(buf)

    try:
        transpile(qc, coupling_map=coupling_map)
    except Exception as exc:  # noqa: BLE001 — reported, not a bug in our code
        return StaticResult(
            parsed=True,
            executed=True,
            transpiled=False,
            circuit_qpy=sandbox_result.circuit_qpy,
            error=ErrorRecord(
                iteration=0,
                stage="static",
                error_type="TranspilationFailure",
                message=str(exc),
            ),
        )

    return StaticResult(
        parsed=True, executed=True, transpiled=True, circuit_qpy=sandbox_result.circuit_qpy
    )
