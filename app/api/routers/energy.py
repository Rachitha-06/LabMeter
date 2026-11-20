from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_deps import require
from app.api.deps import get_session
from app.api.errors import ApiError
from app.api.responses import EmissionFactorOut, TariffOut
from app.db import models as m
from app.services.energy_costs import format_weekdays
from app.services.energy_store import (
    band_from_input, estimate_period, find_overlapping_band, find_overlapping_factor, load_bands, load_factors,
)
from app.utils.time import require_aware
from app.validation.schemas import EmissionFactorIn, TariffIn

router = APIRouter(tags=["energy"])
MAX_WINDOW_DAYS = 400


@router.get("/tariffs", response_model=list[TariffOut], dependencies=[Depends(require("energy:read"))])
def list_tariffs(session: Session = Depends(get_session)):
    return session.scalars(select(m.Tariff).order_by(m.Tariff.effective_from, m.Tariff.start_hour)).all()


@router.post("/tariffs", status_code=201, response_model=TariffOut)
def create_tariff(body: TariffIn, session: Session = Depends(get_session),
                  _: m.User = Depends(require("energy:write"))):
    clash = find_overlapping_band(session, band_from_input(body))
    if clash is not None:
        raise ApiError(409, "tariff_overlap",
                       "this band overlaps an existing one in date, weekday and hours",
                       details={"existing_tariff_id": clash.id})
    row = m.Tariff(
        rate_per_kwh=body.rate_per_kwh, currency=body.currency, effective_from=body.effective_from,
        effective_to=body.effective_to, time_band=body.time_band, start_hour=body.start_hour,
        end_hour=body.end_hour, weekdays=format_weekdays(body.weekdays), source=body.source,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.get("/emission-factors", response_model=list[EmissionFactorOut], dependencies=[Depends(require("energy:read"))])
def list_factors(session: Session = Depends(get_session)):
    return session.scalars(select(m.EmissionFactor).order_by(m.EmissionFactor.effective_from)).all()


@router.post("/emission-factors", status_code=201, response_model=EmissionFactorOut)
def create_factor(body: EmissionFactorIn, session: Session = Depends(get_session),
                  _: m.User = Depends(require("energy:write"))):
    clash = find_overlapping_factor(session, body.effective_from, body.effective_to)
    if clash is not None:
        raise ApiError(409, "factor_overlap", "an emission factor already applies to part of this period",
                       details={"existing_factor_id": clash.id})
    row = m.EmissionFactor(**body.model_dump())
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.get("/estimates/cost-emissions", dependencies=[Depends(require("analytics:read"))])
def cost_and_emissions(
    start: datetime,
    end: datetime,
    granularity: str = Query("day", pattern="^(day|week|month)$"),
    lab_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    try:
        start_utc, end_utc = require_aware(start, "start"), require_aware(end, "end")
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc))
    if end_utc <= start_utc:
        raise ApiError(422, "validation_error", "end must be after start")
    if (end_utc - start_utc).days > MAX_WINDOW_DAYS:
        raise ApiError(422, "window_too_large", f"window must be at most {MAX_WINDOW_DAYS} days")

    labs = session.scalars(select(m.Laboratory).where(
        *( [m.Laboratory.id == lab_id] if lab_id is not None else [] ))).all()
    if lab_id is not None and not labs:
        raise ApiError(404, "lab_not_found", f"laboratory {lab_id} does not exist")
    if not load_bands(session):
        raise ApiError(422, "no_tariff",
                       "no electricity tariff is configured. Add the tariff bands from your tariff order first.")
    if not load_factors(session):
        raise ApiError(422, "no_emission_factor",
                       "no emission factor is configured. Add a factor with its source and year first.")
    result = estimate_period(session, [lab.id for lab in labs], start_utc, end_utc, granularity)
    return {**result, "laboratories": [lab.name for lab in labs]}
