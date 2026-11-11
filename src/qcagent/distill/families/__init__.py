"""The pilot's four training families (family 2, the modular adder, was cut)."""

from qcagent.distill.families.base import (
    BuilderDisagreement,
    Check,
    Family,
    Variation,
    Verification,
)
from qcagent.distill.families.biased_bits import BiasedBits
from qcagent.distill.families.diagonal_phase import DiagonalPhase
from qcagent.distill.families.graph_states import GraphStates
from qcagent.distill.families.kickback import KickbackBvDj
from qcagent.distill.families.pauli_energy import PauliEnergy
from qcagent.distill.families.permutations import QubitPermutations
from qcagent.distill.families.qaoa import QaoaP1
from qcagent.distill.families.qft import QFT

PILOT_FAMILIES: tuple[Family, ...] = (
    QubitPermutations(),
    GraphStates(),
    PauliEnergy(),
    BiasedBits(),
)

#: The seven training families (distill-family-selection-v2.md, "Approved set"). Order is the
#: registered greedy order; `independent_biased_bits` is dropped from training.
PRODUCTION_FAMILIES: tuple[Family, ...] = (
    QubitPermutations(),
    GraphStates(),
    PauliEnergy(),
    DiagonalPhase(),
    KickbackBvDj(),
    QaoaP1(),
    QFT(),
)

__all__ = [
    "PRODUCTION_FAMILIES",
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
