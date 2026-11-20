"""Pure functions that turn meter data into interval consumption.

No database access here, so every rule can be unit-tested directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Sequence

INTERVAL_BASELINE = "baseline"
INTERVAL_OK = "ok"
INTERVAL_RESET = "reset_assumed"
INTERVAL_GAP = "gap"


@dataclass(frozen=True)
class CumulativePoint:
    timestamp: datetime  # must be timezone-aware
    cumulative_kwh: Decimal


@dataclass(frozen=True)
class IntervalResult:
    timestamp: datetime  # end of the interval
    interval_kwh: Optional[Decimal]
    status: str


def cumulative_to_intervals(
    points: Sequence[CumulativePoint], expected_step: timedelta
) -> list[IntervalResult]:
    """Convert cumulative meter readings into interval consumption.

    Rules:
    - The first point is a baseline and yields no interval.
    - An increase yields interval = current - previous (status "ok").
    - A decrease is treated as a meter reset to zero. The interval is the new cumulative value,
      flagged "reset_assumed", because a faulty meter can look the same.
    - A gap longer than 1.5 x expected_step cannot be placed in one period. The interval is left
      empty (status "gap") rather than guessed. The cumulative values remain available for audit.
    - Duplicate or naive timestamps raise ValueError.
    """
    if expected_step <= timedelta(0):
        raise ValueError("expected_step must be positive")

    for point in points:
        if point.timestamp.tzinfo is None or point.timestamp.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")

    ordered = sorted(points, key=lambda p: p.timestamp)
    for previous, current in zip(ordered, ordered[1:]):
        if previous.timestamp == current.timestamp:
            raise ValueError(f"duplicate timestamp: {current.timestamp.isoformat()}")

    results: list[IntervalResult] = []
    previous_point: Optional[CumulativePoint] = None
    for point in ordered:
        if previous_point is None:
            results.append(IntervalResult(point.timestamp, None, INTERVAL_BASELINE))
        elif point.timestamp - previous_point.timestamp > expected_step * 1.5:
            results.append(IntervalResult(point.timestamp, None, INTERVAL_GAP))
        else:
            delta = point.cumulative_kwh - previous_point.cumulative_kwh
            if delta < 0:
                results.append(IntervalResult(point.timestamp, point.cumulative_kwh, INTERVAL_RESET))
            else:
                results.append(IntervalResult(point.timestamp, delta, INTERVAL_OK))
        previous_point = point
    return results
