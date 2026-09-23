"""The closed error taxonomy stays closed, in all three places it lives.

Bug 20: `NonUnitaryCircuit` was added to data-model.md's table and emitted by
`semantic.py`, but never added to `critic.py`'s routing sets. `route_action`
raised `ValueError: unroutable error_type` — loudly and correctly, which is
the good part — but it raised two hours into a live 360-run suite, because
nothing checked the lists against each other beforehand.

The defence that existed was a runtime guard. The defence that was missing is
this file: the type list, the routing table and the spec are three
hand-maintained places, and a check that walks all three turns "someone will
forget" from a certainty into an impossibility.
"""

import re
from pathlib import Path

import pytest

from qcagent.nodes.critic import route_action
from qcagent.state import ERROR_TAXONOMY, ErrorRecord, ResourceResult, SemanticResult, StaticResult
from qcagent.validators.static import _classify_sandbox_failure

DATA_MODEL = Path("specs/001-qcircuit-agent/data-model.md")


def _spec_taxonomy() -> set[str]:
    """The `error_type` column of data-model.md's taxonomy table."""
    rows = re.findall(
        r"^\| `([A-Za-z]+)` \| (?:static|semantic|resource) \|", DATA_MODEL.read_text(), re.M
    )
    assert rows, "the taxonomy table in data-model.md did not parse — has its format changed?"
    return set(rows)


def _static_error(error_type: str) -> StaticResult:
    return StaticResult(
        parsed=True,
        executed=False,
        transpiled=False,
        error=ErrorRecord(iteration=1, stage="static", error_type=error_type, message="x"),
    )


@pytest.mark.parametrize("error_type", sorted(ERROR_TAXONOMY))
def test_every_taxonomy_entry_is_routable(error_type: str) -> None:
    """The check bug 20 was missing. `route_action` raises on an unknown
    type, so an unroutable entry fails here instead of mid-run."""
    if error_type == "ResourceExcess":
        state = (
            None,
            None,
            None,
            ResourceResult(
                depth=90, cx_count=90, width=2, depth_ratio=9.0, cx_ratio=9.0, passed=False
            ),
        )
    elif error_type in ("AssertionViolated", "AssertionNotEvaluable"):
        # These are read off assertion_results, not off a static error; they
        # have dedicated routing tested in test_critic_assertions.py. Here we
        # only need them to be KNOWN to the routing table.
        assert error_type in _routing_known_types()
        return
    elif error_type in ("EndiannessSwap", "WrongGateDecomposition", "ConceptualAlgorithmError"):
        semantic = SemanticResult(
            passed=False,
            verification_method="statevector",
            error=ErrorRecord(iteration=1, stage="semantic", error_type=error_type, message="x"),
        )
        state = (None, None, semantic, None)
    else:
        state = (_static_error(error_type), None, None, None)

    action, routed = route_action(*state, 1, 5, [])

    assert routed == error_type
    assert action in ("retry_retrieval", "retry_generation", "optimize", "abort")


def _routing_known_types() -> set[str]:
    from qcagent.nodes.critic import _RETRY_GENERATION_ERRORS, _RETRY_RETRIEVAL_ERRORS

    return set(_RETRY_RETRIEVAL_ERRORS) | set(_RETRY_GENERATION_ERRORS) | {"ResourceExcess"}


def test_routing_table_and_taxonomy_are_the_same_set() -> None:
    """Neither direction is acceptable: an unrouted type crashes a run, and a
    routed type that is not in the taxonomy is dead code hiding a rename."""
    assert _routing_known_types() == set(ERROR_TAXONOMY)


def test_spec_table_matches_the_code() -> None:
    """data-model.md calls the taxonomy "fechada por definição — categoria
    nova exige emenda ao spec". This is what makes that sentence true rather
    than aspirational."""
    assert _spec_taxonomy() == set(ERROR_TAXONOMY)


def test_the_static_classifier_only_emits_known_types() -> None:
    samples = [
        "NameError: name 'QuantumCircuit' is not defined",
        "NameError: name 'Frobnicator' is not defined",
        "ImportError: cannot import name 'CNOTGate' from 'qiskit.circuit.library'",
        "AttributeError: 'QuantumCircuit' object has no attribute 'hadamard'",
        "CircuitError: 'Index 5 out of range for size 2'",
        "RuntimeError: code did not define `qc`",
    ]
    for stderr in samples:
        assert _classify_sandbox_failure(stderr) in ERROR_TAXONOMY, stderr
