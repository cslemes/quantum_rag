"""The skill histogram obeys the fairness boundary: statements of the 96 in-family tasks
only; never a reference circuit; never a held-out task, not even opened."""

from __future__ import annotations

import builtins
import json
from pathlib import Path

import yaml

from qcagent.distill import skills

ROOT = Path(__file__).resolve().parents[2]


def _opened_during(fn) -> set[str]:
    opened: set[str] = set()
    real_open = builtins.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes

    def spy_open(file, *a, **k):
        opened.add(str(file))
        return real_open(file, *a, **k)

    def spy_read_text(self, *a, **k):
        opened.add(str(self))
        return real_read_text(self, *a, **k)

    def spy_read_bytes(self, *a, **k):
        opened.add(str(self))
        return real_read_bytes(self, *a, **k)

    builtins.open = spy_open  # type: ignore[assignment]
    Path.read_text = spy_read_text  # type: ignore[method-assign]
    Path.read_bytes = spy_read_bytes  # type: ignore[method-assign]
    try:
        fn()
    finally:
        builtins.open = real_open
        Path.read_text = real_read_text  # type: ignore[method-assign]
        Path.read_bytes = real_read_bytes  # type: ignore[method-assign]
    return opened


def test_exactly_the_96_in_family_statements_are_used() -> None:
    held_out = set(
        yaml.safe_load((ROOT / "bench" / "heldout.yaml").read_text())["heldout"]["tasks"]
    )
    statements = skills.in_family_statements()
    assert len(statements) == 96 and not (set(statements) & held_out)


def test_no_held_out_task_and_no_reference_circuit_is_opened() -> None:
    held_out = set(
        yaml.safe_load((ROOT / "bench" / "heldout.yaml").read_text())["heldout"]["tasks"]
    )
    opened = _opened_during(lambda: skills.histogram())
    assert not [p for p in opened if "oracles" in p.replace("\\", "/")]
    assert not [p for p in opened if Path(p).stem in held_out]
    assert any(p.endswith("heldout.yaml") for p in opened)  # it needed the NAMES, only


def test_the_histogram_on_file_is_what_the_statements_give() -> None:
    on_file = json.loads((ROOT / "bench" / "skill_histogram.json").read_text())
    assert on_file["statements"] == 96
    assert on_file["skills"] == skills.histogram()


def test_every_skill_is_named_by_at_least_one_statement() -> None:
    assert all(row["count"] >= 1 for row in skills.histogram())
