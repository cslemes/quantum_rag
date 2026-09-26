"""Mechanism metrics for the corpus/corrector arms (T114).

    uv run python -m analysis.symbol_arms results/<S0>/runs.jsonl [results/<S1>/runs.jsonl ...]

Scores each run file on the metrics registered BEFORE any arm ran
(report-notes.md, "PREDIÇÃO REGISTRADA — corpus na versão fixada"), per
stratum of `config.subset.yaml`:

- m1  corpus-taught errors: attempts failing on a symbol the 2.x corpus
      documented and 1.2.4 lacks (`analysis/data/corpus_2x_only.json`), or
      "'module' object is not callable" (`grover_operator`, F24).
- m2  same-symbol repeat rate: of the transitions ImportError(s) -> next
      attempt, the fraction whose next attempt imports `s` again (F25).
- m3  compila@1 (control for the corrector: it acts on attempts >= 2).
- m4  success rate and exhausted-MAX_ITER rate.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from analysis.metrics import _first_attempt_reached
from bench.runner import iter_records
from bench.schema import RunRecord

STRATUM_A = {
    "dj_constant_4q",
    "dj_constant_4q_perturbed",
    "dj_balanced_4q",
    "simon_6q_perturbed",
    "grover_3q",
    "grover_4q",
    "ising_weighted_maxcut_4q",
    "ising_field_coupling_4q_perturbed",
}
STRATUM_B = {
    "bell_phi_plus_2q",
    "ghz_5q",
    "qft_5q",
    "w_state_5q",
    "qpe_4q",
    "bv_4q",
    "reversible_half_adder_4q",
    "qaoa_maxcut_4q_perturbed",
}

_IMPORT_RE = re.compile(r"ImportError: cannot import name '([^']+)'")
_ATTR_RE = re.compile(r"AttributeError: .* has no attribute '([^']+)'")
_DATA = Path(__file__).parent / "data" / "corpus_2x_only.json"


def _corpus_2x() -> tuple[set[str], set[str]]:
    data = json.loads(_DATA.read_text())
    top = {d.rsplit(".", 1)[-1] if d.startswith("qiskit.") else d for d in data["failures"]}
    members = {d.split(".", 1)[1] for d in data["member_warnings"]}
    return top, members


def is_corpus_taught(message: str, top: set[str], members: set[str]) -> bool:
    if "'module' object is not callable" in message:
        return True
    if (m := _IMPORT_RE.match(message)) and m.group(1) in top:
        return True
    return bool((m := _ATTR_RE.match(message)) and m.group(1) in members)


def score(records: list[RunRecord]) -> dict[str, float | int | None]:
    top, members = _corpus_2x()
    attempts = [e for r in records for e in r.error_history]
    taught = sum(1 for e in attempts if is_corpus_taught(e["message"], top, members))

    repeats = transitions = 0
    for r in records:
        for a, b in zip(r.error_history, r.error_history[1:], strict=False):
            if (ma := _IMPORT_RE.match(a["message"])) is None:
                continue
            transitions += 1
            mb = _IMPORT_RE.match(b["message"])
            repeats += bool(mb and mb.group(1) == ma.group(1))
    # Same definition as the baseline's "esgotou MAX_ITER": used every
    # iteration and did not succeed (config.subset.yaml: max_iter=5).
    exhausted = sum(1 for r in records if r.status != "success" and r.iterations >= 5)
    n = len(records)
    return {
        "runs": n,
        "error_attempts": len(attempts),
        "m1_corpus_taught": taught,
        "m1_runs_with_any": sum(
            1
            for r in records
            if any(is_corpus_taught(e["message"], top, members) for e in r.error_history)
        ),
        "m2_transitions": transitions,
        "m2_repeats": repeats,
        "m2_rate": repeats / transitions if transitions else None,
        "m3_compiles_at_1": sum(_first_attempt_reached(r, "static") for r in records) / n
        if n
        else None,
        "m4_success": sum(r.status == "success" for r in records),
        "m4_exhausted": exhausted,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for path in args.runs:
        records = [
            r
            for r in iter_records(path)
            if r.status not in ("infrastructure_error", "harness_error")
        ]
        excluded = sum(1 for _ in iter_records(path)) - len(records)
        print(f"== {path} ({excluded} infrastructure/harness excluded)")
        for name, stratum in (("A", STRATUM_A), ("B", STRATUM_B)):
            print(f"  stratum {name}: {score([r for r in records if r.task_id in stratum])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
