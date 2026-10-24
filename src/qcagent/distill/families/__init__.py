"""The pilot's four training families (family 2, the modular adder, was cut)."""

from qcagent.distill.families.base import (
    BuilderDisagreement,
    Check,
    Family,
    Variation,
    Verification,
)
from qcagent.distill.families.biased_bits import BiasedBits
from qcagent.distill.families.graph_states import GraphStates
from qcagent.distill.families.pauli_energy import PauliEnergy
from qcagent.distill.families.permutations import QubitPermutations

PILOT_FAMILIES: tuple[Family, ...] = (
    QubitPermutations(),
    GraphStates(),
    PauliEnergy(),
    BiasedBits(),
)

__all__ = [
    "PILOT_FAMILIES",
    "BiasedBits",
    "BuilderDisagreement",
    "Check",
    "Family",
    "GraphStates",
    "PauliEnergy",
    "QubitPermutations",
    "Variation",
    "Verification",
]
