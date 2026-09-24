"""Generated code never executes in the main process (constitution).

The rule is class-quantified and normative, and until now nothing enforced it.
`tests/unit/test_sandbox.py` covers what the sandbox DOES — denylist, timeout,
worker recycling — but nothing asserted that no other code path bypasses it.
That is the gap F11 predicts: a class-quantified rule with no mechanism looks
finished precisely because it is well stated and sits in the constitution.

Enforced by AST rather than grep, the same way test_architecture.py enforces
Principle I: a string search is fooled by a comment, and this rule is too
important to be checked by something that can be fooled by a comment.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The ONE place allowed to execute generated code, because it is the process
# that exists to be sacrificed: a forked worker with a denylist, a timeout,
# and recycling.
SANDBOX = "src/qcagent/validators/sandbox.py"

SOURCE_DIRS = ("src", "bench", "analysis", "scripts")
DANGEROUS = {"exec", "eval", "compile"}


def _dangerous_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in DANGEROUS:
                found.append(f"{node.func.id}() at line {node.lineno}")
    return found


def test_only_the_sandbox_executes_code() -> None:
    offenders = {}
    for directory in SOURCE_DIRS:
        for path in sorted((ROOT / directory).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel == SANDBOX:
                continue
            if calls := _dangerous_calls(path):
                offenders[rel] = calls

    assert not offenders, (
        "generated code must NEVER execute in the main process (constitution, "
        f"Restrições operacionais). Found: {offenders}. If a new execution path is "
        f"genuinely needed, it belongs in {SANDBOX}, which is forked, denylisted, "
        "timed out and recycled — not in the process holding the verdict."
    )


def test_the_sandbox_itself_still_does_execute() -> None:
    """Guards against the test passing because the sandbox stopped working:
    a rule enforced by 'nobody does X' is satisfied trivially if X never
    happens anywhere, including where it must."""
    assert _dangerous_calls(ROOT / SANDBOX), (
        "the sandbox is supposed to be the one place that executes generated "
        "code; if it no longer does, this whole check is vacuous"
    )


def test_verification_reads_qpy_rather_than_re_running_code() -> None:
    """The second half of the same rule. Semantic and resource checks
    deserialize the artifact static_check produced; they never re-execute
    `state["code"]`, which would be a second, unsandboxed execution."""
    graph = (ROOT / "src/qcagent/graph.py").read_text()
    assert "_load_generated_circuit" in graph
    assert "qpy.load" in graph or "_load_generated_circuit" in graph
