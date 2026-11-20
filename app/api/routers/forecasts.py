from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_deps import require
from app.api.deps import get_session, lab_or_404
from app.api.errors import ApiError
from app.api.responses import ForecastDetailOut, ForecastSummaryOut
from app.db import models as m
from app.ml.baseline import InsufficientHistory, forecast_day
from app.ml.registry import ModelUnavailable
from app.services.forecasting import (
    HISTORY_DAYS, MODEL_NAME, MODEL_VERSION, NOTE, OutsideTrainingWindow, evaluate_baseline, load_hourly_series,
    machine_learning_forecast,
)
from app.validation.schemas import ForecastCreate

router = APIRouter(prefix="/forecasts", tags=["forecasting"])


def _detail(record: m.ForecastRecord) -> dict:
    out = ForecastSummaryOut.model_validate(record).model_dump()
    out["details"] = json.loads(record.details_json or "{}")
    return out


@router.post("", status_code=201, response_model=ForecastDetailOut)
def create_forecast(body: ForecastCreate, request: Request,
                    actor: m.User = Depends(require("forecasts:create")),
                    session: Session = Depends(get_session)):
    lab = lab_or_404(session, body.lab_id)
    if body.model != "baseline":
        return _create_ml_forecast(body, lab, request, actor, session)
    series, reading_types = load_hourly_series(
        session, lab, start_day=body.target_date - timedelta(days=HISTORY_DAYS),
        end_day=body.target_date - timedelta(days=1))
    try:
        result = forecast_day(series, body.target_date, k=body.comparable_days, min_history=body.min_history)
    except InsufficientHistory as exc:
        raise ApiError(422, "insufficient_history", str(exc), details=exc.details)
    if result["total_kwh"] is None:
        raise ApiError(
            422, "insufficient_history",
            "the earlier comparable days have no readings for some hours, so a full-day forecast cannot be made",
            details={"missing_hours": result["missing_hours"], "comparable_days": result["comparable_days"]},
        )

    tz = ZoneInfo(lab.timezone)
    horizon_start = datetime.combine(body.target_date, time(0), tzinfo=tz)
    horizon_end = horizon_start + timedelta(days=1)

    details = {
        "target_date": body.target_date.isoformat(),
        "timezone": lab.timezone,
        "hours_local": list(range(24)),
        "hourly_kwh": [round(v, 4) for v in result["hourly"]],
        "total_kwh": round(result["total_kwh"], 4),
        "comparable_days": result["comparable_days"],
        "comparable_days_requested": body.comparable_days,
        "min_history": body.min_history,
        "reading_types_in_history": reading_types,
        "note": NOTE,
    }
    record = m.ForecastRecord(
        lab_id=lab.id,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        predicted_kwh=round(result["total_kwh"], 4),
        details_json=json.dumps(details),
        created_by=actor.id,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return _detail(record)


def _create_ml_forecast(body: ForecastCreate, lab: m.Laboratory, request: Request,
                        actor: m.User, session: Session) -> dict:
    registry = request.app.state.model_registry
    try:
        result = machine_learning_forecast(session, lab, body.target_date, body.model, registry)
    except ModelUnavailable as exc:
        raise ApiError(503, "model_unavailable", str(exc))
    except OutsideTrainingWindow as exc:
        raise ApiError(422, "outside_training_window", str(exc), details=exc.details)
    except InsufficientHistory as exc:
        raise ApiError(422, "insufficient_history", str(exc), details=exc.details)

    tz = ZoneInfo(lab.timezone)
    horizon_start = datetime.combine(body.target_date, time(0), tzinfo=tz)
    details = {
        "target_date": body.target_date.isoformat(),
        "timezone": lab.timezone,
        "hours_local": list(range(24)),
        "hourly_kwh": [round(v, 4) for v in result["hourly"]],
        "total_kwh": round(result["total_kwh"], 4),
        "reading_types_in_history": result["reading_types"],
        "model": {"name": result["model_name"], "version": result["model_version"],
                  "trained_on": result["trained_on"]},
        "note": "Model estimate from earlier readings, calendar and schedule. Not measured consumption.",
    }
    record = m.ForecastRecord(
        lab_id=lab.id, model_name=result["model_name"], model_version=result["model_version"],
        horizon_start=horizon_start, horizon_end=horizon_start + timedelta(days=1),
        predicted_kwh=round(result["total_kwh"], 4), details_json=json.dumps(details), created_by=actor.id,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return _detail(record)


@router.get("", response_model=list[ForecastSummaryOut], dependencies=[Depends(require("forecasts:read"))])
def list_forecasts(lab_id: int | None = None, limit: int = Query(50, ge=1, le=200),
                   session: Session = Depends(get_session)):
    query = select(m.ForecastRecord)
    if lab_id is not None:
        query = query.where(m.ForecastRecord.lab_id == lab_id)
    return session.scalars(query.order_by(m.ForecastRecord.id.desc()).limit(limit)).all()


# Declared before /{forecast_id} so that "evaluation" is not read as an id.
@router.get("/evaluation", dependencies=[Depends(require("forecasts:read"))])
def evaluation(lab_id: int, session: Session = Depends(get_session)):
    lab = lab_or_404(session, lab_id)
    series, _ = load_hourly_series(session, lab)
    if not series:
        raise ApiError(422, "insufficient_history", "this laboratory has no readings to evaluate")
    try:
        return {"lab_id": lab.id, "lab_name": lab.name, **evaluate_baseline(series, lab.timezone)}
    except InsufficientHistory as exc:
        raise ApiError(422, "insufficient_history", str(exc), details=exc.details)
    except ValueError as exc:
        raise ApiError(422, "insufficient_history", str(exc))


@router.get("/{forecast_id}", response_model=ForecastDetailOut, dependencies=[Depends(require("forecasts:read"))])
def get_forecast(forecast_id: int, session: Session = Depends(get_session)):
    record = session.get(m.ForecastRecord, forecast_id)
    if record is None:
        raise ApiError(404, "forecast_not_found", f"forecast {forecast_id} does not exist")
    return _detail(record)
