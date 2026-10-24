"""The held-out slice is the output of a stated rule, not a list someone typed.

bench/heldout.yaml records the rule's result; this re-applies the rule to the
task files and requires the same families, so a change to either side is seen.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = re.compile(r"(ghz|ising|qubo_ising|field_coupling|zstring)")
QUOTAS = {"unitary": 2, "energy": 1, "statevector": 4}


def _pool() -> dict[str, dict]:
    families: dict[str, dict] = {}
    for path in sorted((ROOT / "bench" / "tasks").glob("*/*.json")):
        task = json.loads(path.read_text())
        if EXCLUDED.match(task["task_id"]):
            continue
        name = re.sub(r"_\d+q.*$", "", re.sub(r"_perturbed$", "", task["task_id"]))
        family = families.setdefault(name, {"kind": task["oracle_kind"], "tasks": [], "pf": set()})
        family["tasks"].append(task["task_id"])
        if task.get("perturbed"):
            family["pf"].add(task["perturbation_family"])
    return families


def _apply_rule(salt: str) -> list[str]:
    pool = _pool()
    chosen: list[str] = []
    for kind, quota in QUOTAS.items():
        names = sorted(
            (n for n, f in pool.items() if f["kind"] == kind),
            key=lambda n: hashlib.sha256((salt + n).encode()).hexdigest(),
        )
        chosen += names[:quota]
    return chosen


def test_pool_is_the_66_tasks_outside_ghz_and_ising() -> None:
    assert sum(len(f["tasks"]) for f in _pool().values()) == 66


def test_the_recorded_slice_is_what_the_rule_produces() -> None:
    recorded = yaml.safe_load((ROOT / "bench" / "heldout.yaml").read_text())["heldout"]
    assert sorted(recorded["families"]) == sorted(_apply_rule(recorded["salt"]))
    pool = _pool()
    tasks = sorted(t for n in recorded["families"] for t in pool[n]["tasks"])
    assert tasks == sorted(recorded["tasks"])
    assert hashlib.sha256("\n".join(tasks).encode()).hexdigest() == recorded["tasks_sha256"]


def test_the_rule_s_own_checks_hold() -> None:
    recorded = yaml.safe_load((ROOT / "bench" / "heldout.yaml").read_text())["heldout"]
    pool = _pool()
    assert 6 <= len(recorded["families"]) <= 8
    assert 20 <= recorded["task_count"] <= 30
    by_kind: dict[str, int] = defaultdict(int)
    perturbation_families: set[str] = set()
    for name in recorded["families"]:
        by_kind[pool[name]["kind"]] += 1
        perturbation_families |= pool[name]["pf"]
    assert dict(by_kind) == QUOTAS
    assert len(perturbation_families) >= 3
    assert any(t.endswith("_perturbed") for t in recorded["tasks"])
    assert any(not t.endswith("_perturbed") for t in recorded["tasks"])
