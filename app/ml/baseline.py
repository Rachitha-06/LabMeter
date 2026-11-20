"""Baseline forecast: average the same hour on the most recent comparable days.

"Comparable" means the same day of the week, strictly before the target day. Using only earlier days
means no future value can reach a forecast.

Known limits (addressed in Phase 6 with calendar features):
- Holidays and exam periods are not excluded, so an unusual day in the history can shift the average.
- The average is not weighted by recency.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

Series = dict  # date -> list of 24 floats (kWh per local hour), None where no reading exists


class InsufficientHistory(Exception):
    def __init__(self, message: str, details: dict):
        super().__init__(message)
        self.details = details


def comparable_days(series: Series, target: date, k: int) -> list[date]:
    candidates = sorted(d for d in series if d < target and d.weekday() == target.weekday())
    return candidates[-k:]


def forecast_day(series: Series, target: date, k: int = 4, min_history: int = 2) -> dict:
    """Return 24 hourly predictions for target. Hours with no comparable data are None."""
    if k < 1 or min_history < 1 or min_history > k:
        raise ValueError("require 1 <= min_history <= k")
    comparable = comparable_days(series, target, k)
    if len(comparable) < min_history:
        raise InsufficientHistory(
            f"only {len(comparable)} earlier {target.strftime('%A')}s are available; {min_history} are required",
            {"target_date": target.isoformat(), "comparable_days_found": len(comparable),
             "required": min_history},
        )

    hourly: list[Optional[float]] = []
    for hour in range(24):
        values = [series[d][hour] for d in comparable if series[d][hour] is not None]
        hourly.append(sum(values) / len(values) if values else None)

    missing = [h for h, v in enumerate(hourly) if v is None]
    total = None if missing else sum(hourly)
    return {
        "hourly": hourly,
        "total_kwh": total,
        "missing_hours": missing,
        "comparable_days": [d.isoformat() for d in comparable],
    }
