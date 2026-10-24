"""What a teacher run costs: estimated at the start, measured per call.

The hosted price is TIME-VARYING: input (cache miss) $0.15/Mtok off-peak and
$0.30 peak, output $0.60 and $1.20, with peak at 01:00-04:00 and 06:00-10:00 UTC
on weekdays. So a price read once at the start is wrong for a run that crosses a
boundary. Therefore:

* the start-time estimate is kept for the estimate only, and labelled with the
  window it was taken in;
* the ACTUAL is the sum of `usage.cost` per call, which is authoritative. A call
  whose response carries no cost is priced from its tokens at the rates of the
  window it was made in, and is labelled `computed`, never mixed in silently;
* the run stops, and reports, when the actual passes `factor` times the estimate.

The rates are operator-stated (2026-10-24). The pricing endpoint's path was not
confirmed, so they were not read from it; per-call `usage.cost` is the check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

RATES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "off-peak": (0.15, 0.60),
    "peak": (0.30, 1.20),
}
RATES_SOURCE = "operator-stated 2026-10-24; pricing endpoint path unconfirmed"
PEAK_UTC_HOURS = ((1, 4), (6, 10))  # [start, end) on weekdays
STOP_FACTOR = 3.0


class SpendExceeded(RuntimeError):
    """Actual spend passed the stop factor times the estimate."""


def window_at(moment: datetime) -> str:
    moment = moment.astimezone(UTC)
    if moment.weekday() < 5 and any(a <= moment.hour < b for a, b in PEAK_UTC_HOURS):
        return "peak"
    return "off-peak"


def cost_from_tokens(input_tokens: int, output_tokens: int, window: str) -> float:
    rate_in, rate_out = RATES_USD_PER_MTOK[window]
    return (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000


@dataclass(frozen=True)
class Estimate:
    usd: float
    window: str  # the window the estimate was taken in
    taken_at: str
    rates_usd_per_mtok: tuple[float, float]
    rates_source: str
    basis: str  # what the number rests on


def estimate_from_tokens(
    n_calls: int, input_tokens_per_call: int, output_tokens_per_call: int, *, now: datetime
) -> Estimate:
    window = window_at(now)
    usd = n_calls * cost_from_tokens(input_tokens_per_call, output_tokens_per_call, window)
    return Estimate(
        usd=round(usd, 4),
        window=window,
        taken_at=now.astimezone(UTC).isoformat(timespec="seconds"),
        rates_usd_per_mtok=RATES_USD_PER_MTOK[window],
        rates_source=RATES_SOURCE,
        basis=(
            f"{n_calls} calls x ({input_tokens_per_call} in + {output_tokens_per_call} out "
            f"tokens) at the {window} rates"
        ),
    )


@dataclass
class SpendGuard:
    estimate_usd: float
    factor: float = STOP_FACTOR
    actual_usd: float = 0.0
    calls: int = 0
    computed_calls: int = 0  # calls priced from tokens because usage.cost was absent
    by_window: dict[str, float] = field(default_factory=dict)
    last_usd: float = 0.0
    last_source: str = ""

    @property
    def ceiling_usd(self) -> float:
        return self.estimate_usd * self.factor

    def add(
        self,
        *,
        reported_cost: Any,
        input_tokens: int,
        output_tokens: int,
        at: datetime,
    ) -> tuple[float, str]:
        """Record one call. Returns (usd, source) with source 'usage.cost' or
        'computed'. Raises SpendExceeded AFTER recording, so the call that crossed
        the line is counted."""
        window = window_at(at)
        if isinstance(reported_cost, int | float) and not isinstance(reported_cost, bool):
            usd, source = float(reported_cost), "usage.cost"
        else:
            usd, source = cost_from_tokens(input_tokens, output_tokens, window), "computed"
            self.computed_calls += 1
        self.last_usd, self.last_source = usd, source
        self.actual_usd += usd
        self.calls += 1
        self.by_window[window] = self.by_window.get(window, 0.0) + usd
        if self.actual_usd > self.ceiling_usd:
            raise SpendExceeded(
                f"actual ${self.actual_usd:.4f} is over {self.factor:g}x the "
                f"${self.estimate_usd:.4f} estimate (ceiling ${self.ceiling_usd:.4f}) "
                f"after {self.calls} calls; stopping to report"
            )
        return usd, source

    def report(self) -> dict[str, Any]:
        return {
            "estimate_usd": self.estimate_usd,
            "actual_usd": round(self.actual_usd, 6),
            "actual_over_estimate": (
                round(self.actual_usd / self.estimate_usd, 3) if self.estimate_usd else None
            ),
            "stop_factor": self.factor,
            "calls": self.calls,
            "calls_priced_from_tokens": self.computed_calls,
            "actual_by_window_usd": {k: round(v, 6) for k, v in self.by_window.items()},
        }
