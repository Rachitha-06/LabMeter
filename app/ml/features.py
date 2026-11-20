"""Features for the machine-learning models. Training and serving both call this module.

Every feature for (day D, hour h) uses only information available at the start of day D:
- earlier days' readings (lags and a recent same-hour average),
- the academic calendar and the operating schedule for day D (both known in advance),
- static laboratory facts (computer count and recorded equipment load).

Deliberately excluded: occupancy and session bookings (no data exists yet), and any reading from day D itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

# is_weekend is not a feature: it is an exact combination of the weekday indicators, which would make
# a linear model's design matrix rank-deficient.
FEATURE_NAMES = [
    "hour", "weekday", "month", "is_holiday", "is_exam_period",
    "scheduled_open", "scheduled_hours", "computer_count", "rated_load_kw",
    "lag_1d", "lag_2d", "lag_7d", "mean_7d_same_hour",
]
CATEGORICAL = ["hour", "weekday", "month"]
REQUIRED = ["lag_1d", "lag_2d", "lag_7d", "mean_7d_same_hour"]
NAN = float("nan")


@dataclass(frozen=True)
class CalendarDay:
    is_holiday: bool
    is_exam_period: bool


@dataclass(frozen=True)
class ScheduleEntry:
    weekday: int
    open_hour: int
    close_hour: int
    valid_from: date
    valid_to: Optional[date]


@dataclass(frozen=True)
class LabContext:
    lab_id: int
    computer_count: int
    rated_load_kw: float
    schedules: tuple = field(default_factory=tuple)  # ScheduleEntry values


def scheduled_window(ctx: LabContext, day: date) -> Optional[tuple[int, int]]:
    for entry in ctx.schedules:
        if entry.weekday != day.weekday():
            continue
        if entry.valid_from <= day and (entry.valid_to is None or day <= entry.valid_to):
            return entry.open_hour, entry.close_hour
    return None


def _value(series: dict, day: date, hour: int) -> Optional[float]:
    row = series.get(day)
    return None if row is None else row[hour]


def features_for_hour(series: dict, ctx: LabContext, day: date, hour: int,
                      calendar: dict[date, CalendarDay]) -> dict:
    cal = calendar.get(day, CalendarDay(False, False))
    window = scheduled_window(ctx, day)
    lags = [_value(series, day - timedelta(days=k), hour) for k in range(1, 8)]
    past = [v for v in lags if v is not None]
    return {
        "hour": hour,
        "weekday": day.weekday(),
        "month": day.month,
        "is_holiday": int(cal.is_holiday),
        "is_exam_period": int(cal.is_exam_period),
        "scheduled_open": int(window is not None and window[0] <= hour < window[1]),
        "scheduled_hours": (window[1] - window[0]) if window else 0,
        "computer_count": ctx.computer_count,
        "rated_load_kw": ctx.rated_load_kw,
        "lag_1d": NAN if lags[0] is None else lags[0],
        "lag_2d": NAN if lags[1] is None else lags[1],
        "lag_7d": NAN if lags[6] is None else lags[6],
        "mean_7d_same_hour": sum(past) / len(past) if len(past) >= 3 else NAN,
    }


def build_rows(series: dict, ctx: LabContext, calendar: dict, days: list[date]) -> list[dict]:
    """Training rows: hours with a known target and every required lag. Others are dropped."""
    rows = []
    for day in days:
        if day not in series:
            continue
        for hour in range(24):
            target = series[day][hour]
            if target is None:
                continue
            features = features_for_hour(series, ctx, day, hour, calendar)
            if any(math.isnan(features[name]) for name in REQUIRED):
                continue
            rows.append({**features, "lab_id": ctx.lab_id, "day": day, "target": target})
    return rows


def features_for_day(series: dict, ctx: LabContext, day: date, calendar: dict) -> tuple[list[dict], list[int]]:
    """Serving: one feature row per local hour. Returns the rows and the hours that cannot be predicted."""
    rows, missing = [], []
    for hour in range(24):
        features = features_for_hour(series, ctx, day, hour, calendar)
        if any(math.isnan(features[name]) for name in REQUIRED):
            missing.append(hour)
        rows.append(features)
    return rows, missing
