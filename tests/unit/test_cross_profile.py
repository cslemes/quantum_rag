"""The registered derivation of the attempt-1 depth, and the stuck-code control."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from analysis.cross_profile import _bootstrap, depth_at_1, load_bins, stuck


def _record(errors: list[dict], hashes: list[str] | None = None, status: str = "failed_static"):
    trace = [{"node": "generator", "code_sha256_16": h} for h in (hashes or ["a"])]
    return SimpleNamespace(error_history=errors, trace=trace, status=status)


def _err(kind: str, stage: str = "static", message: str = "", iteration: int = 1) -> dict:
    return {"iteration": iteration, "stage": stage, "error_type": kind, "message": message}


@pytest.mark.parametrize(
    ("error", "level"),
    [
        (_err("DeprecatedAPI"), 0),
        (_err("GenerationTruncated"), 0),
        (_err("SyntaxError", message="invalid syntax (<unknown>, line 1)"), 0),
        (_err("SyntaxError", message="TypeError: unsupported operand type(s) for +="), 1),
        (_err("MissingImport"), 1),
        (_err("UnknownSymbol"), 1),
        (_err("HallucinatedSymbol"), 1),
        (_err("QubitIndexError"), 1),
        (_err("TranspilationFailure"), 2),
        (_err("CircuitSerializationFailure"), 2),
        (_err("WrongGateDecomposition", stage="semantic"), 3),
        (_err("DepthExceeded", stage="resource"), 3),
        (_err("ParameterBindingError"), 3),
    ],
)
def test_registered_levels(error: dict, level: int) -> None:
    assert depth_at_1(_record([error])) == level


def test_no_error_at_attempt_1_is_level_4_and_later_errors_do_not_count() -> None:
    assert depth_at_1(_record([])) == 4
    assert depth_at_1(_record([_err("UnknownSymbol", iteration=2)])) == 4


def test_no_generator_call_has_no_depth() -> None:
    record = SimpleNamespace(error_history=[], trace=[{"node": "planner"}], status="rejected_input")
    assert depth_at_1(record) is None


def test_an_unregistered_error_type_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError, match="no registered level"):
        depth_at_1(_record([_err("SomethingNew")]))


def test_stuck_is_five_attempts_with_one_code() -> None:
    assert stuck(_record([], ["a"] * 5))
    assert not stuck(_record([], ["a"] * 4))
    assert not stuck(_record([], ["a", "a", "a", "a", "b"]))


def test_bins_are_the_registered_sizes() -> None:
    assert {k: len(v) for k, v in load_bins("strict").items()} == {"0": 19, "1": 59, "2+": 42}
    assert {k: len(v) for k, v in load_bins("general").items()} == {"0": 1, "1": 71, "2+": 48}


def test_bootstrap_is_reproducible_and_brackets_the_mean() -> None:
    values = [0.0, 1.0, 1.0, 2.0, -1.0, 0.0, 1.0, 0.0]
    low, high = _bootstrap(values)
    assert (low, high) == _bootstrap(values)
    assert low < sum(values) / len(values) < high
