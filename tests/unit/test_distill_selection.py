"""The capacities in the family selection are arithmetic, cross-checked by enumeration."""

from __future__ import annotations

import json
from itertools import combinations, permutations
from pathlib import Path

from qcagent.distill import selection

ROOT = Path(__file__).resolve().parents[2]


def test_permutation_count_matches_enumeration() -> None:
    assert selection.permutations_count(3, 5) == sum(
        sum(1 for _ in permutations(range(n))) - 1 for n in (3, 4, 5)
    )
    assert selection.permutations_count() == 5905


def test_graph_counts_match_the_enumerated_ghz_experiment() -> None:
    assert selection.connected_graph_count(4) == 38 and selection.connected_graph_count(5) == 728
    assert selection.stabilizer_graph_count() == 27470


def test_simon_count_matches_enumeration() -> None:
    def brute(n: int) -> int:
        return sum(bin(s).count("1") for s in range(1, 2**n))

    assert selection.simon_count(2, 4) == sum(brute(n) for n in (2, 3, 4))
    assert selection.simon_count() == 320


def test_pauli_string_count_matches_enumeration() -> None:
    n = 3
    strings = {
        "".join(c)
        for c in __import__("itertools").product("IXYZ", repeat=n)
        if 1 <= sum(ch != "I" for ch in c) <= 3
    }
    assert len(strings) == selection.pauli_string_count(n) == 63


def test_grover_count_for_a_small_case() -> None:
    assert selection.grover_count(3, 3, 3) == len(list(combinations(range(8), 1))) + len(
        list(combinations(range(8), 2))
    ) + len(list(combinations(range(8), 3)))


def test_the_capacities_on_file_are_what_the_code_computes() -> None:
    on_file = json.loads((ROOT / "bench" / "family_selection_capacity.json").read_text())
    assert on_file["capacity"] == {name: fn() for name, fn in selection.CAPACITY.items()}
