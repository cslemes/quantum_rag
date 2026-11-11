"""What every training family provides, and the rule that decides if it may be used.

A family either has a CLOSED FORM, which is then the oracle and the circuit
builders are independent constructions checked against it, or it has none, in
which case two independent constructions check each other and analytic limit
cases calibrate both. A family whose checks disagree is not usable: `verify_all`
raises `BuilderDisagreement` and the registry takes statements only from
families that passed it.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from qiskit import QuantumCircuit


class BuilderDisagreement(RuntimeError):
    """A builder and its oracle, or two builders, disagree. The family is not
    used until the disagreement is resolved and recorded."""


@dataclass(frozen=True)
class Variation:
    family: str
    index: int
    params: dict[str, Any]

    @property
    def key(self) -> str:
        """Structural identity: family plus canonical parameters."""
        payload = json.dumps(
            {"family": self.family, "params": self.params}, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Check:
    name: str
    passed: bool
    max_abs_diff: float = 0.0
    detail: str = ""


@dataclass
class Verification:
    variation: Variation
    checks: list[Check] = field(default_factory=list)

    @property
    def agreed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)


class Family(ABC):
    name: str
    oracle_kind: str  # unitary | statevector | energy | distribution
    #: the oracle is a closed form (True) or an exact diagonalisation (False)
    closed_form: bool

    @abstractmethod
    def variations(self) -> list[Variation]: ...

    @abstractmethod
    def statement(self, v: Variation) -> str: ...

    @abstractmethod
    def verify(self, v: Variation) -> Verification: ...

    @abstractmethod
    def accepts(self, v: Variation, circuit: QuantumCircuit) -> Check:
        """Does a candidate circuit (a teacher's, later) meet this variation's
        oracle? Uses the strict comparison for unitary/statevector: the
        endianness-tolerant checks of the cascade are not used on training data."""

    def calibrate(self) -> list[Check]:
        """Analytic limit cases both builders must reproduce. Default none."""
        return []

    def verify_all(self, count: int | None = None) -> list[Verification]:
        """Check the calibration and every variation that will be used: the first `count`
        (the family's pilot default when None). Admitting more than was verified is not allowed."""
        failed: list[str] = []
        results = []
        for check in self.calibrate():
            if not check.passed:
                failed.append(f"calibration {check.name}: {check.detail}")
        variations = self.variations() if count is None else self.variations(count)  # type: ignore[call-arg]
        for v in variations:
            result = self.verify(v)
            results.append(result)
            failed += [
                f"{v.key} {c.name}: {c.detail or c.max_abs_diff}"
                for c in result.checks
                if not c.passed
            ]
        if failed:
            raise BuilderDisagreement(f"{self.name}: " + "; ".join(failed[:5]))
        return results
