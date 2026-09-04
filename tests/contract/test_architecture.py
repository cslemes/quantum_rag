"""Architecture test for Constitution Principle I: `validators/` must never
import from `llm/`. Every verdict on correctness must come from
deterministic, re-executable code — never from an LLM.
"""

import ast
from pathlib import Path

VALIDATORS_DIR = Path(__file__).parents[2] / "src" / "qcagent" / "validators"
FORBIDDEN_MODULE_PREFIX = "qcagent.llm"


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_validators_do_not_import_llm() -> None:
    violations: dict[str, set[str]] = {}
    for path in sorted(VALIDATORS_DIR.rglob("*.py")):
        modules = _imported_modules(path.read_text())
        forbidden = {
            m
            for m in modules
            if m == FORBIDDEN_MODULE_PREFIX or m.startswith(f"{FORBIDDEN_MODULE_PREFIX}.")
        }
        if forbidden:
            violations[str(path.relative_to(VALIDATORS_DIR.parents[2]))] = forbidden

    assert not violations, (
        "src/qcagent/validators/ must never import from qcagent.llm "
        f"(Constitution Principle I): {violations}"
    )


def test_validators_directory_exists_and_is_non_empty() -> None:
    # Guards against the test above passing vacuously if the directory is
    # ever emptied or renamed.
    assert VALIDATORS_DIR.is_dir()
    assert list(VALIDATORS_DIR.glob("*.py"))
