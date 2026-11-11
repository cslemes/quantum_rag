"""The leakage gate and the statement registry it guards (phase 1).

The registry is the only writer of training statements. Generation takes
registry ids, never strings: a statement that is not in the registry with a
`pass` verdict cannot be generated or exported, and an entry is only ever made
by `admit_family`, which first requires the family's builders to agree.

Measures in phase 1, against all 120 test tasks:
  * LEXICAL: Jaccard over normalised word 5-grams, exact (80 x 120 pairs).
  * STRUCTURAL: a (family, parameters) key may be registered once. (v1 also refused a
    training family whose id is a task-id family of the suite. That rule enforced the
    family-held-out slice, dropped by decision 2 on 2026-10-27, and fired on a name
    coincidence: it rejected all of the `qft` training family. Removed 2026-11-10;
    `structural-key-v2`. This changes the gate version, so entries admitted under v1,
    such as pilot-v1's registry, are stale by design.)
  * CIRCUIT-LEVEL, after generation: an accepted circuit is compared, strictly,
    with every reference of the same width and kind (`circuit_leak_check`).
The semantic (embedding) measure is phase 2 and every reject log says so.

Thresholds are CALIBRATED on the suite's own 60 canonical/perturbed twin pairs
and its cross-family pairs (`calibrate`), and the result is recorded in
`bench/leakage_calibration.json`. The first design said "reject anything at
least as close as the LEAST similar twin pair". Measured, that twin is at
Jaccard 0.0076 (a perturbation that rewrites the whole prompt), so that rule
would reject nearly everything; and the 5th percentile of twins (0.051) is
below the 95th percentile of cross-family pairs (0.122): lexically, twins and
unrelated tasks overlap. So the lexical measure is used for what it can do, find
copies and light edits: REJECT at the median twin Jaccard, REVIEW from the 95th
percentile of cross-family test-vs-test pairs. What lexical similarity cannot see
(a perturbed rewrite) is the semantic measure's job, in phase 2.

The gate version is a hash of the test set's content (every task file and every
oracle file) plus the measure definitions. Any change to the 120 invalidates
every earlier pass; `export` re-runs the gate and refuses on any difference.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from qiskit import QuantumCircuit, qpy

from qcagent.distill.families.base import Family, Variation
from qcagent.distill.strict import circuit_state, circuit_unitary, states_equal, unitaries_equal

ROOT = Path(__file__).resolve().parents[3]
TASKS_DIR = ROOT / "bench" / "tasks"
CALIBRATION_PATH = ROOT / "bench" / "leakage_calibration.json"
MEASURES = "lexical-jaccard-word5gram-v1;structural-key-v2;circuit-strict-v1"
NGRAM = 5
SEMANTIC_NOTE = "not measured (phase 2)"


class NotAdmitted(RuntimeError):
    """A statement id that is not in the registry with a pass verdict."""


class GateStale(RuntimeError):
    """The test set changed since a statement passed."""


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def grams(text: str, n: int = NGRAM) -> frozenset[tuple[str, ...]]:
    words = _words(text)
    return frozenset(tuple(words[i : i + n]) for i in range(max(len(words) - n + 1, 1)))


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def task_family(task_id: str) -> str:
    return re.sub(r"_\d+q.*$", "", re.sub(r"_perturbed$", "", task_id))


def load_test_tasks(tasks_dir: Path = TASKS_DIR) -> dict[str, dict[str, Any]]:
    tasks = {}
    for path in sorted(tasks_dir.glob("*/*.json")):
        task = json.loads(path.read_text(encoding="utf-8"))
        tasks[task["task_id"]] = task
    return tasks


def test_set_hash(tasks: dict[str, dict[str, Any]], root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for task_id in sorted(tasks):
        digest.update(json.dumps(tasks[task_id], sort_keys=True).encode())
        oracle = root / tasks[task_id]["oracle_path"]
        digest.update(oracle.read_bytes() if oracle.exists() else b"<missing oracle>")
    return digest.hexdigest()


@dataclass(frozen=True)
class Calibration:
    reject_at: float  # lexical Jaccard >= this: reject
    review_at: float  # lexical Jaccard >= this (and < reject_at): human review
    twin_pairs: int
    twin_min: float
    twin_p5: float
    twin_median: float
    cross_pairs: int
    cross_p95: float
    cross_max: float
    test_set_hash: str
    measures: str = MEASURES


def calibrate(tasks: dict[str, dict[str, Any]], root: Path = ROOT) -> Calibration:
    g = {t: grams(d["prompt"]) for t, d in tasks.items()}
    twins = [jaccard(g[t], g[d["base_task_id"]]) for t, d in tasks.items() if d.get("perturbed")]
    ids = sorted(tasks)
    cross = [
        jaccard(g[a], g[b])
        for i, a in enumerate(ids)
        for b in ids[i + 1 :]
        if task_family(a) != task_family(b)
    ]
    return Calibration(
        reject_at=float(np.median(twins)),
        review_at=float(np.percentile(cross, 95)),
        twin_pairs=len(twins),
        twin_min=float(np.min(twins)),
        twin_p5=float(np.percentile(twins, 5)),
        twin_median=float(np.median(twins)),
        cross_pairs=len(cross),
        cross_p95=float(np.percentile(cross, 95)),
        cross_max=float(np.max(cross)),
        test_set_hash=test_set_hash(tasks, root),
    )


@dataclass(frozen=True)
class Neighbour:
    task_id: str
    score: float


def nearest(statement: str, test_grams: dict[str, frozenset], k: int = 3) -> list[Neighbour]:
    mine = grams(statement)
    scored = sorted(
        (Neighbour(t, round(jaccard(mine, g), 6)) for t, g in test_grams.items()),
        key=lambda n: (-n.score, n.task_id),
    )
    return scored[:k]


def statement_id(statement: str) -> str:
    return hashlib.sha256(statement.encode()).hexdigest()[:16]


class StatementRegistry:
    """Only writer of training statements. One JSON line per statement."""

    def __init__(
        self,
        path: Path,
        *,
        tasks_dir: Path = TASKS_DIR,
        root: Path = ROOT,
        calibration: Calibration | None = None,
    ) -> None:
        self.path = path
        self.reject_log = path.with_suffix(".rejects.jsonl")
        self.tasks = load_test_tasks(tasks_dir)
        self.test_grams = {t: grams(d["prompt"]) for t, d in self.tasks.items()}
        self.calibration = calibration or calibrate(self.tasks, root)
        self.gate_version = hashlib.sha256(
            f"{self.calibration.test_set_hash}|{MEASURES}".encode()
        ).hexdigest()[:16]

    # -- reading -----------------------------------------------------------

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line]

    def require_pass(self, sid: str) -> dict[str, Any]:
        """The only way generation gets a statement: by id, only if it passed
        and the gate is still the one it passed."""
        for entry in self.entries():
            if entry["id"] == sid:
                if entry["verdict"] != "pass":
                    raise NotAdmitted(f"{sid}: verdict is {entry['verdict']!r}, not 'pass'")
                if entry["gate_version"] != self.gate_version:
                    raise GateStale(f"{sid}: passed under gate {entry['gate_version']}")
                return entry
        raise NotAdmitted(f"{sid}: not in the registry")

    def export(self) -> list[dict[str, Any]]:
        """Re-run the gate on every statement and refuse on any failure; nothing
        that bypassed admission can be exported."""
        out = []
        for entry in self.entries():
            if entry["verdict"] != "pass":
                continue
            if entry["gate_version"] != self.gate_version:
                raise GateStale(f"{entry['id']}: passed under gate {entry['gate_version']}")
            again = self._judge(entry["statement"], entry["family"])
            if again["verdict"] == "reject":
                raise NotAdmitted(f"{entry['id']}: fails the gate on re-run: {again['reasons']}")
            out.append(entry)
        return out

    # -- writing -----------------------------------------------------------

    def admit_family(self, family: Family, count: int | None = None) -> list[dict[str, Any]]:
        """Admit a family's statements (its first `count` variations; the family's pilot
        default when None). `verify_all` raises `BuilderDisagreement` first: a family whose
        builders disagree admits nothing."""
        family.verify_all(count)
        variations = family.variations() if count is None else family.variations(count)  # type: ignore[call-arg]
        return [self._admit(family, v) for v in variations]

    def record_review(self, sid: str, decision: str, reviewer: str) -> None:
        if decision not in ("accept", "reject"):
            raise ValueError("decision must be 'accept' or 'reject'")
        entries = self.entries()
        for entry in entries:
            if entry["id"] == sid and entry["verdict"] == "review":
                entry["verdict"] = "pass" if decision == "accept" else "reject"
                entry["reviewer"] = {"decision": decision, "by": reviewer}
                self.path.write_text("".join(json.dumps(e) + "\n" for e in entries))
                if decision == "reject":
                    self._log_reject(entry, ["reviewer rejected"])
                return
        raise NotAdmitted(f"{sid}: no entry awaiting review")

    def _judge(self, statement: str, family_name: str) -> dict[str, Any]:
        neighbours = nearest(statement, self.test_grams)
        top = neighbours[0].score
        reasons = []
        if top >= self.calibration.reject_at:
            reasons.append(f"lexical {top} >= reject {self.calibration.reject_at:.4f}")
        verdict = "reject" if reasons else "pass"
        if verdict == "pass" and top >= self.calibration.review_at:
            verdict = "review"
            reasons.append(f"lexical {top} >= review {self.calibration.review_at:.4f}")
        return {"verdict": verdict, "reasons": reasons, "nearest": [asdict(n) for n in neighbours]}

    def _admit(self, family: Family, v: Variation) -> dict[str, Any]:
        statement = family.statement(v)
        sid = statement_id(statement)
        existing = {e["id"]: e for e in self.entries()}
        keys = {e["variation_key"] for e in existing.values()}
        if sid in existing:
            return existing[sid]
        judged = self._judge(statement, family.name)
        if v.key in keys:
            judged = {**judged, "verdict": "reject", "reasons": ["structural: duplicate key"]}
        entry = {
            "id": sid,
            "statement": statement,
            "family": family.name,
            "oracle_kind": family.oracle_kind,
            "variation_key": v.key,
            "params": v.params,
            "builders_verified": True,
            "gate_version": self.gate_version,
            "semantic": SEMANTIC_NOTE,
            **judged,
        }
        with self.path.open("a") as sink:
            sink.write(json.dumps(entry) + "\n")
        if entry["verdict"] == "reject":
            self._log_reject(entry, entry["reasons"])
        return entry

    def _log_reject(self, entry: dict[str, Any], reasons: list[str]) -> None:
        """Scores and ids only, so this log can ship without copying test text."""
        record = {
            "statement_hash": entry["id"],
            "nearest": entry["nearest"],
            "thresholds": {
                "reject_at": self.calibration.reject_at,
                "review_at": self.calibration.review_at,
            },
            "reasons": reasons,
            "reviewer_decision": entry.get("reviewer"),
            "gate_version": self.gate_version,
            "measures": MEASURES,
            "semantic": SEMANTIC_NOTE,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with self.reject_log.open("a") as sink:
            sink.write(json.dumps(record) + "\n")


def review_queue(
    registry: StatementRegistry, *, top: int = 100, random_below: int = 50, seed: int = 1
) -> dict[str, list[dict[str, Any]]]:
    """The pairs a human looks at: the closest `top` overall (or all if fewer),
    plus a random sample from below the review band to measure what the gate
    misses. Scores and ids; the statements are in the registry."""
    pairs = []
    for entry in registry.entries():
        mine = grams(entry["statement"])
        for task_id, g in registry.test_grams.items():
            pairs.append({"id": entry["id"], "task_id": task_id, "score": jaccard(mine, g)})
    pairs.sort(key=lambda p: (-p["score"], p["id"], p["task_id"]))
    below = [p for p in pairs[top:] if p["score"] < registry.calibration.review_at]
    sample = random.Random(seed).sample(below, min(random_below, len(below)))
    return {"closest": pairs[:top], "random_below_band": sample}


def circuit_leak_check(
    oracle_kind: str,
    circuit: QuantumCircuit,
    *,
    tasks: dict[str, dict[str, Any]] | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    """After generation: is an accepted circuit equivalent (strictly, up to
    global phase) to a reference of the same width and kind? The answer can leak
    even when the statement's text does not. Only unitary and statevector
    references are circuits; for energy and distribution there is nothing of the
    kind to compare, and the result says so instead of passing silently."""
    if oracle_kind not in ("unitary", "statevector"):
        return {
            "evaluated": False,
            "matches": [],
            "reason": f"no circuit references for {oracle_kind}",
        }
    tasks = tasks or load_test_tasks()
    matches = []
    for task_id, task in sorted(tasks.items()):
        if task["oracle_kind"] != oracle_kind or task["n_qubits"] != circuit.num_qubits:
            continue
        with open(root / task["oracle_path"], "rb") as f:
            (reference,) = qpy.load(f)
        if oracle_kind == "unitary":
            same = unitaries_equal(circuit_unitary(reference), circuit_unitary(circuit)).equal
        else:
            same = states_equal(circuit_state(reference), circuit_state(circuit)).equal
        if same:
            matches.append(task_id)
    return {"evaluated": True, "matches": matches, "reason": ""}
