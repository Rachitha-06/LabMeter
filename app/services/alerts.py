"""Storing alerts, the review workflow, and explanations. Rules live in alert_rules.py."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.utils.time import as_utc
from app.services.alert_rules import RULE_ID, Candidate, run_rule
from app.services.forecasting import load_calendar, load_hourly_series, load_lab_context

STATUSES = ("open", "under_review", "resolved")
TRANSITIONS = {
    ("open", "under_review"),
    ("open", "resolved"),
    ("under_review", "resolved"),
    ("under_review", "open"),
    ("resolved", "open"),
}


class InvalidTransition(Exception):
    pass


def local_to_utc(day: date, hour: int, tz: ZoneInfo) -> datetime:
    """UTC instant of a local wall-clock hour on a day.

    Raises ValueError for a local hour that does not exist (the skipped hour when clocks go forward).
    An ambiguous hour (clocks going back) resolves to its first occurrence (fold=0).
    """
    naive = datetime.combine(day, time(0)) + timedelta(hours=hour)
    aware = naive.replace(tzinfo=tz)
    utc = aware.astimezone(timezone.utc)
    if utc.astimezone(tz).replace(tzinfo=None) != naive:
        raise ValueError(f"{naive.isoformat()} does not exist in {tz.key} (clocks move forward that day)")
    return utc


def explanation_for(lab_name: str, candidate: Candidate, tz: ZoneInfo) -> str:
    start = local_to_utc(candidate.day, candidate.start_hour, tz).astimezone(tz)
    end = local_to_utc(candidate.day, candidate.end_hour - 1, tz).astimezone(tz) + timedelta(hours=1)
    excess = candidate.excess_kwh
    return (
        f"{lab_name} used {candidate.actual_kwh:.2f} kWh between {start:%H:%M} and {end:%H:%M} on "
        f"{start:%A %d %b %Y}, outside its scheduled hours. Earlier comparable days used "
        f"{candidate.expected_kwh:.2f} kWh over the same hours, an excess of {excess:.2f} kWh. "
        "This is a suspected excess for review, not a confirmed waste. Possible explanations include "
        "equipment left running, an unrecorded schedule change, or a meter fault."
    )


@dataclass
class DetectionSummary:
    created: int = 0
    already_recorded: int = 0
    labs: int = 0
    labs_without_schedule: int = 0
    days_evaluated: int = 0
    days_skipped_exam: int = 0
    days_skipped_holiday: int = 0
    hours_without_history: int = 0
    hours_without_reading: int = 0

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def detect_alerts(session: Session, *, lab_id: Optional[int] = None, start: Optional[date] = None,
                  end: Optional[date] = None) -> dict:
    """Run the rule over stored readings and record new alerts. Re-running never duplicates an alert."""
    query = select(m.Laboratory).order_by(m.Laboratory.id)
    if lab_id is not None:
        query = query.where(m.Laboratory.id == lab_id)
    calendar = load_calendar(session)
    summary = DetectionSummary()
    for lab in session.scalars(query).all():
        series, _ = load_hourly_series(session, lab)
        if not series:
            continue
        summary.labs += 1
        days = {d for d in series if (start is None or d >= start) and (end is None or d <= end)}
        run = run_rule(series, load_lab_context(session, lab), calendar, days)
        if run.skipped_no_schedule:
            summary.labs_without_schedule += 1
            continue
        summary.days_evaluated += run.days_evaluated
        summary.days_skipped_exam += run.days_skipped_exam
        summary.days_skipped_holiday += run.days_skipped_holiday
        summary.hours_without_history += run.hours_without_history
        summary.hours_without_reading += run.hours_without_reading

        tz = ZoneInfo(lab.timezone)
        recorded = {as_utc(start) for start in session.scalars(select(m.Alert.period_start).where(
            m.Alert.lab_id == lab.id, m.Alert.rule_id == RULE_ID)).all()}
        for candidate in run.candidates:
            period_start = local_to_utc(candidate.day, candidate.start_hour, tz)
            if period_start in recorded:
                summary.already_recorded += 1
                continue
            recorded.add(period_start)
            session.add(m.Alert(
                lab_id=lab.id,
                period_start=period_start,
                period_end=local_to_utc(candidate.day, candidate.end_hour - 1, tz) + timedelta(hours=1),
                actual_kwh=round(candidate.actual_kwh, 4),
                expected_kwh=round(candidate.expected_kwh, 4),
                rule_id=RULE_ID,
                severity=candidate.severity,
                status="open",
                explanation=explanation_for(lab.name, candidate, tz),
            ))
            summary.created += 1
    session.commit()
    return summary.as_dict()


def transition(session: Session, alert: m.Alert, to_status: str, comment: Optional[str],
               user_id: Optional[int]) -> m.AlertReview:
    if to_status not in STATUSES:
        raise InvalidTransition(f"unknown status '{to_status}'")
    if (alert.status, to_status) not in TRANSITIONS:
        raise InvalidTransition(f"an alert cannot move from '{alert.status}' to '{to_status}'")
    if to_status == "resolved" and not (comment and comment.strip()):
        raise InvalidTransition("a comment explaining the resolution is required")
    review = m.AlertReview(alert_id=alert.id, user_id=user_id, from_status=alert.status,
                           to_status=to_status, comment=(comment or "").strip() or None)
    alert.status = to_status
    session.add(review)
    session.commit()
    session.refresh(review)
    return review


def add_comment(session: Session, alert: m.Alert, comment: str, user_id: Optional[int]) -> m.AlertReview:
    review = m.AlertReview(alert_id=alert.id, user_id=user_id, from_status=alert.status,
                           to_status=alert.status, comment=comment.strip())
    session.add(review)
    session.commit()
    session.refresh(review)
    return review
