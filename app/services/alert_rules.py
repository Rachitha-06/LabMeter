"""Rule-based wastage screening. Pure functions: no database access.

Rule `unoccupied_excess_v1`
- Looks at local hours outside the scheduled opening hours of the laboratory.
- Expects the same hour on up to four earlier comparable days of the same weekday to be the reference.
  A comparable day must be an ordinary teaching day: not a holiday, not an exam period.
- Flags an hour when actual use exceeds that reference by at least MIN_EXCESS_KWH and by at least
  RELATIVE_EXCESS of the reference.
- An hour that this rule flagged on an earlier day is excluded from later references. Otherwise one
  anomalous day would make the next comparable day look normal.
- Joins consecutive flagged hours on the same day into one period.

The rule flags suspected excess for review. It never decides that wastage occurred.
Thresholds are fixed defaults. They were set before any evaluation and were not tuned on the labels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from app.ml.features import CalendarDay, LabContext, scheduled_window

RULE_ID = "unoccupied_excess_v1"
COMPARABLE_DAYS = 4
MIN_COMPARABLE_DAYS = 2
MIN_EXCESS_KWH = 0.5
RELATIVE_EXCESS = 0.5


@dataclass(frozen=True)
class HourFinding:
    day: date
    hour: int
    actual: float
    expected: float
    excess: float
    flagged: bool


@dataclass(frozen=True)
class Candidate:
    day: date
    start_hour: int
    end_hour: int  # exclusive
    actual_kwh: float
    expected_kwh: float
    excess_kwh: float
    severity: str
    hours: tuple


@dataclass
class RuleRun:
    skipped_no_schedule: bool = False
    candidates: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    days_evaluated: int = 0
    days_skipped_exam: int = 0
    days_skipped_holiday: int = 0
    hours_without_reading: int = 0
    hours_without_history: int = 0


def _calendar_day(calendar: dict, day: date) -> CalendarDay:
    return calendar.get(day, CalendarDay(False, False))


def is_ordinary_day(calendar: dict, day: date) -> bool:
    cal = _calendar_day(calendar, day)
    return not cal.is_exam_period and not cal.is_holiday


def is_scheduled_open(ctx: LabContext, day: date, hour: int) -> bool:
    window = scheduled_window(ctx, day)
    return window is not None and window[0] <= hour < window[1]


def severity_for(excess_kwh: float, expected_kwh: float) -> str:
    """Review priority from how large the excess is relative to what was expected. Not a confidence score."""
    ratio = excess_kwh / max(expected_kwh, MIN_EXCESS_KWH)
    if ratio >= 3.0:
        return "high"
    if ratio >= 1.5:
        return "medium"
    return "low"


def _group(day: date, flagged: list[HourFinding]) -> list[Candidate]:
    groups: list[list[HourFinding]] = []
    for finding in sorted(flagged, key=lambda f: f.hour):
        if groups and groups[-1][-1].hour == finding.hour - 1:
            groups[-1].append(finding)
        else:
            groups.append([finding])
    candidates = []
    for group in groups:
        actual = sum(f.actual for f in group)
        expected = sum(f.expected for f in group)
        excess = sum(f.excess for f in group)
        candidates.append(Candidate(
            day=day,
            start_hour=group[0].hour,
            end_hour=group[-1].hour + 1,
            actual_kwh=round(actual, 4),
            expected_kwh=round(expected, 4),
            excess_kwh=round(excess, 4),
            severity=severity_for(excess, expected),
            hours=tuple(f.hour for f in group),
        ))
    return candidates


def run_rule(series: dict, ctx: LabContext, calendar: dict, days: Optional[Iterable[date]] = None) -> RuleRun:
    run = RuleRun()
    if not ctx.schedules:
        # Without operating hours, every hour would look "unoccupied". Refuse to judge rather than flood alerts.
        run.skipped_no_schedule = True
        return run
    wanted = set(days) if days is not None else None
    all_days = sorted(series)
    flagged_before: set[tuple[date, int]] = set()  # (day, hour) flagged on earlier days; never used as reference
    for day in all_days:
        if wanted is not None and day not in wanted:
            continue
        cal = _calendar_day(calendar, day)
        if cal.is_exam_period:
            run.days_skipped_exam += 1
            continue
        if cal.is_holiday:
            run.days_skipped_holiday += 1
            continue
        run.days_evaluated += 1

        comparables = [
            d for d in all_days
            if d < day and d.weekday() == day.weekday() and is_ordinary_day(calendar, d)
        ][-COMPARABLE_DAYS:]

        day_findings: list[HourFinding] = []
        for hour in range(24):
            if is_scheduled_open(ctx, day, hour):
                continue
            actual = series[day][hour]
            if actual is None:
                run.hours_without_reading += 1
                continue
            history = [
                series[d][hour] for d in comparables
                if not is_scheduled_open(ctx, d, hour)
                and series[d][hour] is not None
                and (d, hour) not in flagged_before
            ]
            if len(history) < MIN_COMPARABLE_DAYS:
                run.hours_without_history += 1
                continue
            expected = sum(history) / len(history)
            excess = actual - expected
            flagged = excess >= max(MIN_EXCESS_KWH, RELATIVE_EXCESS * expected)
            day_findings.append(HourFinding(day, hour, actual, expected, excess, flagged))

        run.findings.extend(day_findings)
        flagged_now = [f for f in day_findings if f.flagged]
        flagged_before.update((f.day, f.hour) for f in flagged_now)
        run.candidates.extend(_group(day, flagged_now))
    return run
