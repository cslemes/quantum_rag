"""The retrieval index's pin, and one place that compares an index to it.

The pin (`bench/environment.yaml`, `retrieval_index`) names the collection and
the number of points the measured runs used. The suite runner refuses to start
on a mismatch, and the UI uses the SAME comparison, so that a field showing
the index size has a consumer that can fail: a size displayed and compared to
nothing is decoration (F21).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

PIN_FILE = Path(__file__).resolve().parents[3] / "bench" / "environment.yaml"

IndexState = Literal["ok", "mismatch", "missing", "empty", "unreachable", "not_pinned"]


@dataclass(frozen=True)
class IndexPin:
    collection: str | None
    expected_points: int | None


@dataclass(frozen=True)
class IndexStatus:
    state: IndexState
    points: int | None = None
    expected: int | None = None
    reason: str | None = None

    @property
    def usable(self) -> bool:
        return self.state in ("ok", "not_pinned")

    def summary(self) -> str:
        """One line for a person: the size, and what it was compared with."""
        if self.state == "ok":
            return f"{self.points} documents — matches the pin"
        if self.state == "not_pinned":
            return f"{self.points} documents (no pin to compare with)"
        if self.state == "mismatch":
            return (
                f"REFUSED — {self.points} documents, the pin says {self.expected}: "
                "a different corpus is a different system"
            )
        if self.state == "empty":
            return "REFUSED — EMPTY: run `make index`"
        if self.state == "missing":
            return "REFUSED — no collection: run `make index`"
        return f"REFUSED — unreachable: {self.reason}"


def load_index_pin(pin_file: Path = PIN_FILE) -> IndexPin:
    pin = (yaml.safe_load(pin_file.read_text()) or {}).get("retrieval_index") or {}
    return IndexPin(pin.get("collection"), pin.get("expected_points"))


def index_status(client, pin: IndexPin, collection: str) -> IndexStatus:
    """Classify the live index against the pin. Never raises: an index that
    cannot be asked is an `unreachable` state, not an exception."""
    try:
        if not client.collection_exists(collection):
            return IndexStatus("missing", expected=pin.expected_points)
        points = int(client.count(collection, exact=True).count)
    except Exception as exc:  # noqa: BLE001 - any transport failure is a state
        return IndexStatus("unreachable", expected=pin.expected_points, reason=type(exc).__name__)
    if points == 0:
        return IndexStatus("empty", points=0, expected=pin.expected_points)
    if pin.expected_points is None:
        return IndexStatus("not_pinned", points=points)
    state: IndexState = "ok" if points == pin.expected_points else "mismatch"
    return IndexStatus(state, points=points, expected=pin.expected_points)
