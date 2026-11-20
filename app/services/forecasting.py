"""Turns stored readings into hourly series and runs the baseline forecast and its evaluation.

Hourly values are sums of interval readings within each laboratory-local hour, so a lab with
several meters is forecast as one total. Readings are assumed to be hourly; finer data would be
summed into hours.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.ml.baseline import InsufficientHistory, forecast_day
from app.ml.metrics import mae, rmse
from app.ml.split import split_dates
from app.utils.time import as_utc

MODEL_NAME = "comparable_day_mean"
MODEL_VERSION = "v1"
EVAL_CANDIDATES = (1, 2, 3, 4, 6, 8)
NOTE = "Estimated baseline from earlier comparable days. Not measured consumption."


HISTORY_DAYS = 60  # comparable days (up to 8 weeks) and 7-day lags need no more history than this


def local_midnight_utc(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time(0), tzinfo=tz).astimezone(timezone.utc)


def load_hourly_series(session: Session, lab: m.Laboratory, start_day: Optional[date] = None,
                       end_day: Optional[date] = None) -> tuple[dict, list[str]]:
    """Hourly series for a laboratory. start_day and end_day are local calendar days, both inclusive."""
    tz = ZoneInfo(lab.timezone)
    query = select(m.EnergyReading.timestamp_utc, m.EnergyReading.interval_kwh, m.EnergyReading.reading_type).where(
        m.EnergyReading.lab_id == lab.id)
    if start_day is not None:
        query = query.where(m.EnergyReading.timestamp_utc >= local_midnight_utc(start_day, tz))
    if end_day is not None:
        query = query.where(m.EnergyReading.timestamp_utc < local_midnight_utc(end_day + timedelta(days=1), tz))
    rows = session.execute(query).all()
    sums: dict[tuple[date, int], float] = {}
    types: set[str] = set()
    for ts, kwh, reading_type in rows:
        local = as_utc(ts).astimezone(tz)
        key = (local.date(), local.hour)
        sums[key] = sums.get(key, 0.0) + float(kwh)
        types.add(reading_type)
    series: dict[date, list[Optional[float]]] = {}
    for (day, hour), value in sums.items():
        series.setdefault(day, [None] * 24)[hour] = value
    return series, sorted(types)


def _score_days(series: dict, days: list[date], k: int, min_history: int):
    pairs: list[tuple[float, float]] = []
    daily: list[dict] = []
    skipped = 0
    scored_days = 0
    for day in days:
        try:
            result = forecast_day(series, day, k=k, min_history=min_history)
        except InsufficientHistory:
            skipped += 1
            continue
        actual = series[day]
        day_pairs = [(p, a) for p, a in zip(result["hourly"], actual) if p is not None and a is not None]
        if day_pairs:
            pairs.extend(day_pairs)
            scored_days += 1
        if result["total_kwh"] is not None and all(a is not None for a in actual):
            daily.append({"date": day.isoformat(), "actual_kwh": round(sum(actual), 4),
                          "predicted_kwh": round(result["total_kwh"], 4)})
    return pairs, daily, scored_days, skipped


def evaluate_baseline(series: dict, timezone: str, min_history: int = 2) -> dict:
    """Choose k on the validation period, then report accuracy on the untouched test period."""
    train, validation, test = split_dates(series.keys())

    selection = []
    for k in EVAL_CANDIDATES:
        if k < min_history:
            continue
        pairs, _, days_scored, skipped = _score_days(series, validation, k, min_history)
        if not pairs:
            continue
        selection.append({
            "k": k,
            "mae": round(mae(pairs), 4),
            "rmse": round(rmse(pairs), 4),
            "days_evaluated": days_scored,
            "days_skipped_insufficient_history": skipped,
        })
    if not selection:
        raise InsufficientHistory(
            "no validation day has enough earlier comparable days to evaluate the baseline",
            {"validation_days": len(validation), "min_history": min_history},
        )
    chosen = min(selection, key=lambda r: (r["mae"], r["k"]))

    test_pairs, daily, test_days, test_skipped = _score_days(series, test, chosen["k"], min_history)
    if not test_pairs:
        raise InsufficientHistory(
            "no test day has enough earlier comparable days to evaluate the baseline",
            {"test_days": len(test), "min_history": min_history},
        )
    daily_total_mae = None
    if daily:
        daily_total_mae = round(mae([(d["predicted_kwh"], d["actual_kwh"]) for d in daily]), 4)

    return {
        "model": f"{MODEL_NAME} {MODEL_VERSION}",
        "timezone": timezone,
        "split": {
            "train": {"start": train[0].isoformat(), "end": train[-1].isoformat(), "days": len(train)},
            "validation": {"start": validation[0].isoformat(), "end": validation[-1].isoformat(),
                           "days": len(validation)},
            "test": {"start": test[0].isoformat(), "end": test[-1].isoformat(), "days": len(test)},
        },
        "validation_selection": selection,
        "chosen_k": chosen["k"],
        "test": {
            "mae": round(mae(test_pairs), 4),
            "rmse": round(rmse(test_pairs), 4),
            "hours_evaluated": len(test_pairs),
            "days_evaluated": test_days,
            "days_skipped_insufficient_history": test_skipped,
            "daily_total_mae": daily_total_mae,
        },
        "daily": daily,
        "notes": [
            "k was chosen on the validation period. The test period was not used for any choice.",
            "Each test day is forecast only from days before it, as it would be in operation.",
            "Holidays and exam periods are not excluded from the history yet (Phase 6 addresses this).",
        ],
    }


# ---------------------------------------------------------------------------
# Machine-learning inputs (Phase 6)
# ---------------------------------------------------------------------------

def load_calendar(session: Session) -> dict:
    from app.ml.features import CalendarDay
    return {
        row.day: CalendarDay(row.is_holiday, row.is_exam_period)
        for row in session.scalars(select(m.AcademicCalendarDay))
    }


def load_lab_context(session: Session, lab: m.Laboratory):
    from app.ml.features import LabContext, ScheduleEntry
    equipment = session.scalars(select(m.Equipment).where(m.Equipment.lab_id == lab.id)).all()
    rated_load_kw = sum(
        float(item.quantity) * float(item.rated_power_w) for item in equipment if item.rated_power_w is not None
    ) / 1000.0
    schedules = tuple(
        ScheduleEntry(
            weekday=s.weekday,
            open_hour=s.open_time.hour,   # schedules are assumed to start and end on the hour
            close_hour=s.close_time.hour,
            valid_from=s.valid_from,
            valid_to=s.valid_to,
        )
        for s in session.scalars(select(m.OperatingSchedule).where(m.OperatingSchedule.lab_id == lab.id))
    )
    return LabContext(lab_id=lab.id, computer_count=lab.computer_count, rated_load_kw=rated_load_kw,
                      schedules=schedules)


def load_training_inputs(session: Session):
    from app.ml.training import TrainingInputs
    labs = session.scalars(select(m.Laboratory).order_by(m.Laboratory.id)).all()
    series_by_lab, contexts, names, zones = {}, {}, {}, {}
    for lab in labs:
        series, _ = load_hourly_series(session, lab)
        if not series:
            continue
        series_by_lab[lab.id] = series
        contexts[lab.id] = load_lab_context(session, lab)
        names[lab.id] = lab.name
        zones[lab.id] = lab.timezone
    return TrainingInputs(series_by_lab=series_by_lab, contexts=contexts,
                          calendar=load_calendar(session), lab_names=names, timezones=zones)


class OutsideTrainingWindow(Exception):
    """The requested day was part of the data the model was trained on, so a forecast would only echo it."""

    def __init__(self, message: str, details: dict):
        super().__init__(message)
        self.details = details


def machine_learning_forecast(session: Session, lab: m.Laboratory, target: date, model_key: str,
                              registry) -> dict:
    """Predict one local day with a saved model. Raises ModelUnavailable, InsufficientHistory,
    or OutsideTrainingWindow."""
    from app.ml.features import features_for_day
    from app.ml.training import predict_hours

    model, entry = registry.get(model_key)
    trained_through = date.fromisoformat(entry["trained_on"]["end"])
    if target <= trained_through:
        raise OutsideTrainingWindow(
            f"{target.isoformat()} is inside the period this model was trained on (up to "
            f"{trained_through.isoformat()}). Choose a later day, or use the baseline.",
            {"target_date": target.isoformat(), "trained_through": trained_through.isoformat()},
        )
    series, reading_types = load_hourly_series(
        session, lab, start_day=target - timedelta(days=HISTORY_DAYS), end_day=target - timedelta(days=1))
    context = load_lab_context(session, lab)
    rows, missing = features_for_day(series, context, target, load_calendar(session))
    if missing:
        raise InsufficientHistory(
            "some hours need earlier readings that are not available, so a full-day forecast cannot be made",
            {"target_date": target.isoformat(), "missing_hours": missing},
        )
    hourly = predict_hours(model, rows, entry["prediction_ceiling_kwh"])
    return {
        "hourly": hourly,
        "total_kwh": sum(hourly),
        "reading_types": reading_types,
        "model_name": model_key,
        "model_version": entry["model_version"],
        "trained_on": entry["trained_on"],
    }
