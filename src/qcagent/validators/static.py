"""Static verification — layers 1-2 (executability, transpilability).

See contracts/validators.md and data-model.md's closed error taxonomy.
"""

import ast
import hashlib
import importlib
import io
import re
import types
from dataclasses import dataclass
from functools import lru_cache

from qiskit import __version__ as qiskit_version
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

# Modules whose public names the generator may legitimately use. A NameError
# naming something that lives in one of these is a MISSING IMPORT, not an
# invented symbol — the model wrote correct code and omitted the import line.
_IMPORTABLE_MODULES = (
    "qiskit",
    "qiskit.circuit",
    "qiskit.circuit.library",
    "qiskit.quantum_info",
    "qiskit.transpiler",
    "qiskit.primitives",
    "numpy",
)

# Conventional aliases: `np.sqrt(...)` raises `NameError: name 'np' is not
# defined`, and "np" is not a public name of any module, so the lookup below
# would misclassify it as invented.
_ALIAS_IMPORTS = {"np": "import numpy as np", "plt": "import matplotlib.pyplot as plt"}

_NAME_ERROR_RE = re.compile(r"^NameError: name '([^']+)' is not defined")


@lru_cache(maxsize=1)
def _importable_symbols() -> dict[str, str]:
    """name -> the module it can be imported from. Built once, by importing
    the modules and reading their public namespace, so it can never drift
    from the installed Qiskit the way a hand-written list would."""
    index: dict[str, str] = {}
    for module_name in _IMPORTABLE_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:  # pragma: no cover - a missing optional dependency
            continue
        for name in dir(module):
            # Submodules are excluded: `qiskit.circuit.library.grover_operator`
            # is a MODULE in 1.2.4 (a function in 2.x), importable and not
            # callable. Suggesting `from ... import grover_operator` as a fix
            # would hand the model the exact error F24 traced to the corpus.
            if not name.startswith("_") and not isinstance(
                getattr(module, name, None), types.ModuleType
            ):
                index.setdefault(name, module_name)
    return index


def missing_import_for(stderr: str) -> str | None:
    """The import statement that would fix `stderr`, or None when this is not
    a missing import.

    The distinction this draws is the whole point (F14, F3): a `NameError`
    naming a symbol that EXISTS is a missing import line, and no amount of
    retrieved documentation adds one — `retry_retrieval` is structurally
    incapable of fixing it. A `NameError` (or `ImportError`) naming something
    that does not exist anywhere IS a hallucination, and retrieval is the
    right response there. Both used to be `HallucinatedSymbol`.
    """
    match = _NAME_ERROR_RE.match(stderr)
    if match is None:
        return None
    symbol = match.group(1)
    if symbol in _ALIAS_IMPORTS:
        return _ALIAS_IMPORTS[symbol]
    module = _importable_symbols().get(symbol)
    return f"from {module} import {symbol}" if module else None


_IMPORT_ERROR_RE = re.compile(r"^ImportError: cannot import name '([^']+)' from '([^' ]+)'")

# Other frameworks' names for the same gates (F26). 71% of the invented
# symbols in the baseline were PennyLane operation names, alone or with
# Qiskit's `Gate` suffix appended. They are not misspellings — `Hadamard` and
# `HGate` share nothing a fuzzy matcher could use — so the mapping is a
# vocabulary table, and a small one, because the gate vocabulary is small.
# Only names the normalization below cannot reach are listed.
_VOCABULARY_ALIASES = {
    "CNOT": "CXGate",
    "Hadamard": "HGate",
    "PauliX": "XGate",
    "PauliY": "YGate",
    "PauliZ": "ZGate",
    "Toffoli": "CCXGate",
    "CPHASE": "CPhaseGate",
}


def _normal_key(name: str) -> str:
    """Case, underscores and a trailing `gate` removed: `efficient_su2` and
    `EfficientSU2`, `GraphStateGate` and `GraphState`, `H` and `HGate` all
    collapse to the same key."""
    key = name.lower().replace("_", "")
    return key.removesuffix("gate") or key


@lru_cache(maxsize=1)
def _symbols_by_key() -> dict[str, str]:
    """normal key -> real symbol. On a collision the circuit-library name
    wins (that is where the invented gate names point), then sort order, so
    the choice is deterministic."""
    index = _importable_symbols()
    ranked = sorted(index, key=lambda n: (index[n] != "qiskit.circuit.library", n))
    by_key: dict[str, str] = {}
    for name in ranked:
        by_key.setdefault(_normal_key(name), name)
    return by_key


@dataclass(frozen=True)
class SymbolCorrection:
    symbol: str  # what the code tried to import
    module: str  # where it tried to import it from
    replacement: str  # the real symbol
    replacement_module: str

    @property
    def import_line(self) -> str:
        return f"from {self.replacement_module} import {self.replacement}"

    @property
    def reason(self) -> str:
        if self.replacement == self.symbol:
            return (
                f"`{self.symbol}` is not in `{self.module}`; it is in `{self.replacement_module}`"
            )
        return (
            f"`{self.symbol}` is not a symbol in `{self.module}` (Qiskit {qiskit_version}); "
            f"`{self.replacement}` is"
        )


def symbol_correction_for(stderr: str) -> SymbolCorrection | None:
    """The real symbol an `ImportError` was reaching for, derived from the
    INSTALLED runtime, or None.

    This is negative knowledge the corpus cannot supply (F25): documentation
    describes what exists, so no page says "`H` is not in
    `qiskit.circuit.library`". 104 of the 112 baseline runs that ended on an
    ImportError named a symbol that never existed; retrieval had nothing to
    offer, and the same symbol recurred in 58-68% of transitions. The truth
    source is `_importable_symbols()` — never the indexed symbol list, which
    held 2.x symbols the runtime lacks (F24).
    """
    match = _IMPORT_ERROR_RE.match(stderr)
    if match is None:
        return None
    symbol, module = match.groups()
    return _correct(symbol, module)


def _correct(symbol: str, module: str) -> SymbolCorrection | None:
    index = _importable_symbols()
    if symbol in index:  # real, but imported from the wrong module
        return SymbolCorrection(symbol, module, symbol, index[symbol])
    base = symbol.removesuffix("Gate") or symbol
    candidate = _VOCABULARY_ALIASES.get(symbol) or _VOCABULARY_ALIASES.get(base)
    if candidate is None and f"{symbol}Gate" in index:
        candidate = f"{symbol}Gate"
    if candidate is None:
        candidate = _symbols_by_key().get(_normal_key(symbol))
    if candidate is None or candidate not in index:
        return None
    return SymbolCorrection(symbol, module, candidate, index[candidate])


def import_corrections_for(code: str) -> tuple[list[SymbolCorrection], list[str]]:
    """Every `from M import X` in `code` where X does not exist in M, or is a
    submodule there — not only the first one (T115).

    Python raises on the first failing import, so the error message names one
    symbol; in 5 of 8 S2 runs that ended on an ImportError the code imported
    more than one. Correcting them one per attempt lets a regenerating model
    fix one and reintroduce the other, which is the oscillation S2 measured.

    Returns (corrections, unresolved) — `unresolved` are "`X` from `M`"
    strings with no real neighbour. Only modules in `_IMPORTABLE_MODULES` are
    resolved: the module is imported by its listed name, never by a name the
    generated code chose, and the code itself is only PARSED, never run.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return [], []
    corrections: list[SymbolCorrection] = []
    unresolved: list[str] = []
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.ImportFrom)
            or node.level
            or node.module not in _IMPORTABLE_MODULES
        ):
            continue
        module = importlib.import_module(node.module)
        for alias in node.names:
            obj = getattr(module, alias.name, None)
            if alias.name == "*" or (obj is not None and not isinstance(obj, types.ModuleType)):
                continue
            if (correction := _correct(alias.name, node.module)) is not None:
                corrections.append(correction)
            else:
                unresolved.append(f"`{alias.name}` from `{node.module}`")
    return corrections, unresolved


def _classify_sandbox_failure(stderr: str) -> str:
    """Maps a sandbox execution failure to the closed error taxonomy
    (data-model.md), grounded in plan.md's critic routing table.

    - A NameError naming a symbol that EXISTS in Qiskit/numpy ->
      MissingImport. Checked FIRST, because it is a strict subset of the
      NameError case below and routes to a different action: no amount of
      retrieved documentation adds an import line (F14, F3).
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
    if missing_import_for(stderr) is not None:
        return "MissingImport"
    # An ImportError whose intended symbol the runtime can name. Split from
    # HallucinatedSymbol by the ACTION available, not by whether the name
    # was invented or removed (F25): here the fix is a specific line.
    if symbol_correction_for(stderr) is not None:
        return "UnknownSymbol"
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
    try:
        with io.BytesIO(sandbox_result.circuit_qpy) as buf:
            (qc,) = qpy.load(buf)
    except Exception as exc:  # noqa: BLE001 — a third-party reader, not our logic
        # Bug 21. The sandbox BUILT and SERIALIZED a circuit that Qiskit's own
        # QPY reader then refused: `IndexError: list assignment index out of
        # range` from `read_circuit`'s register reconstruction, on a QAOA task.
        # Unguarded, this escaped the graph and cost a whole run.
        #
        # The trigger is not reproduced — a dozen register- and
        # ParameterVector-shaped circuits round-trip fine — so this is not an
        # explanation, it is containment plus the evidence needed to diagnose
        # the next occurrence. What makes the next one diagnosable is that the
        # run now terminates normally, which means `final_code` is RECORDED;
        # as a harness error it was lost, because that path has no code to
        # report.
        #
        # The fingerprint below identifies the exact bytes without persisting
        # them: QPY is binary and would break JSON serialization (bug 14).
        digest = hashlib.sha256(sandbox_result.circuit_qpy).hexdigest()[:16]
        return StaticResult(
            parsed=True,
            executed=True,
            transpiled=False,
            error=ErrorRecord(
                iteration=0,
                stage="static",
                error_type="CircuitSerializationFailure",
                message=(
                    f"o circuito foi construído mas não sobreviveu ao round-trip QPY: "
                    f"{type(exc).__name__}: {exc}"
                ),
                payload={
                    "qpy_sha256_16": digest,
                    "qpy_bytes": len(sandbox_result.circuit_qpy),
                    "qiskit_version": qiskit_version,
                },
            ),
        )

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
