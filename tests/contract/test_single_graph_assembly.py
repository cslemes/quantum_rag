"""The live graph is assembled in exactly ONE place (T104).

`run_single.py` and `runner.py` each built it independently and had already
drifted: no seed versus explicit seeds, `WorkerPool(size=2)` versus size 6,
`max_qubits=20` written twice, temperature explicit on one side only. Nobody
decided any of that — it accumulated, and it silently made by-hand
observations incomparable to suite numbers for the same task (F20).

The interface (US6) would have been a third copy. A demo that diverges from
the measured system misrepresents it, so this is enforced rather than agreed.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Where assembling the graph by hand is legitimate: the definition itself, the
# single live assembly, and test harnesses that deliberately inject fakes.
ALLOWED = {
    "src/qcagent/graph.py",
    "src/qcagent/live.py",
}
ALLOWED_PREFIXES = ("tests/",)

# Scoped to the source trees rather than the whole repo: an rglob from the
# root walked results/ and .git and took ~59s, and a slow contract test is one
# people learn to skip.
SOURCE_DIRS = ("src", "bench", "analysis", "scripts")


def _calls_build_graph(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_graph"
        for node in ast.walk(tree)
    )


def test_only_one_module_assembles_the_live_graph() -> None:
    offenders = []
    for path in sorted(p for d in SOURCE_DIRS for p in (ROOT / d).rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED or rel.startswith(ALLOWED_PREFIXES) or "/.venv" in rel:
            continue
        if _calls_build_graph(path):
            offenders.append(rel)

    assert not offenders, (
        "these modules assemble the live graph themselves instead of calling "
        f"qcagent.live.build_live_graph: {offenders}. Two assemblies drift — that is "
        "what T104 removed, and a third would make the demo diverge from the "
        "measured system."
    )


def test_the_live_assembly_requires_an_explicit_seed() -> None:
    """A default seed is what produced the drift: two callers silently
    disagreeing while both looked correct."""
    import inspect

    from qcagent.live import build_live_graph

    seed = inspect.signature(build_live_graph).parameters["seed"]
    assert seed.default is inspect.Parameter.empty, "seed must be required, never defaulted"
    assert seed.kind is inspect.Parameter.KEYWORD_ONLY, "seed must be named at every call site"


def test_run_single_can_choose_its_seed() -> None:
    """It could not, before T104 — which is why every by-hand observation was
    locked to 42, a seed the suite never runs."""
    import inspect

    import bench.run_single as rs

    assert "seed" in inspect.signature(rs.run_task).parameters
    source = Path(ROOT / "bench/run_single.py").read_text()
    assert '"--seed"' in source, "the CLI must expose it, not just the function"


def test_run_single_has_no_unprofiled_path() -> None:
    """run_single used to build its client from settings: the one way to
    generate with no profile stamp and no server-version check."""
    import inspect

    import bench.run_single as rs

    source = Path(ROOT / "bench/run_single.py").read_text()
    assert "OllamaClient(" not in source and "settings.ollama" not in source
    assert "build_client(profile)" in source
    param = inspect.signature(rs.run_task).parameters["profile"]
    assert param.default is inspect.Parameter.empty and param.kind is inspect.Parameter.KEYWORD_ONLY
    assert '"--profile"' in source and "required=True" in source


def test_run_single_refuses_an_unusable_profile(monkeypatch) -> None:
    import pytest

    import bench.run_single as rs
    from qcagent.llm.profiles import ProfileError, ProfileStatus

    down = ProfileStatus(profile="local-7b", label="x", state="unreachable", reason="down")
    monkeypatch.setattr(rs, "probe", lambda _p: down)
    with pytest.raises(ProfileError, match="NOT sent to any other profile"):
        rs.gate_profile("local-7b")
