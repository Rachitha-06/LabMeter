from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_deps import require
from app.api.deps import get_session
from app.api.errors import ApiError
from app.api.responses import ReadingCreateOut, ReadingOut, RevisionOut
from app.db import models as m
from app.services.readings_store import store_reading
from app.utils.time import require_aware
from app.validation.schemas import KWH_QUANTUM, ReadingIn, ReadingPatch

router = APIRouter(tags=["readings"])


@router.post("/readings", response_model=ReadingCreateOut, status_code=201, dependencies=[Depends(require("readings:write"))])
def create_reading(body: ReadingIn, response: Response, session: Session = Depends(get_session)):
    lab = session.get(m.Laboratory, body.lab_id)
    if lab is None:
        raise ApiError(404, "lab_not_found", f"laboratory {body.lab_id} does not exist")
    if lab.archived_at is not None:
        raise ApiError(422, "laboratory_archived", "this laboratory is archived; restore it before adding readings")
    outcome = store_reading(session, body)
    if outcome.status == "conflict":
        session.rollback()
        raise ApiError(
            409, "reading_conflict",
            "a different value is already stored for this lab, meter and timestamp. "
            "Correct it with PATCH /api/readings/{id} and a reason.",
            details={
                "existing_reading_id": outcome.existing.id,
                "existing_interval_kwh": str(outcome.existing.interval_kwh),
                "new_interval_kwh": str(body.interval_kwh),
            },
        )
    if outcome.status == "duplicate":
        response.status_code = 200  # nothing was written; the stored row is returned unchanged
        return {"status": "duplicate", "reading": outcome.existing}
    session.commit()
    session.refresh(outcome.reading)
    return {"status": "created", "reading": outcome.reading}


@router.get("/readings", response_model=list[ReadingOut], dependencies=[Depends(require("readings:read"))])
def list_readings(
    lab_id: Optional[int] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    reading_type: Optional[Literal["measured", "imported", "simulated"]] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    query = select(m.EnergyReading)
    if lab_id is not None:
        query = query.where(m.EnergyReading.lab_id == lab_id)
    if start is not None:
        query = query.where(m.EnergyReading.timestamp_utc >= _aware(start, "start"))
    if end is not None:
        query = query.where(m.EnergyReading.timestamp_utc < _aware(end, "end"))
    if reading_type is not None:
        query = query.where(m.EnergyReading.reading_type == reading_type)
    query = query.order_by(m.EnergyReading.timestamp_utc, m.EnergyReading.lab_id).limit(limit).offset(offset)
    return session.scalars(query).all()


@router.get("/readings/{reading_id}", response_model=ReadingOut, dependencies=[Depends(require("readings:read"))])
def get_reading(reading_id: int, session: Session = Depends(get_session)):
    reading = session.get(m.EnergyReading, reading_id)
    if reading is None:
        raise ApiError(404, "reading_not_found", f"reading {reading_id} does not exist")
    return reading


@router.patch("/readings/{reading_id}", response_model=ReadingOut, dependencies=[Depends(require("readings:correct"))])
def correct_reading(reading_id: int, body: ReadingPatch, actor: m.User = Depends(require("readings:correct")),
                    session: Session = Depends(get_session)):
    """Correct the kWh amount. The old value is kept in reading_revisions. Source and type never change."""
    reading = session.get(m.EnergyReading, reading_id)
    if reading is None:
        raise ApiError(404, "reading_not_found", f"reading {reading_id} does not exist")
    old = Decimal(reading.interval_kwh).quantize(KWH_QUANTUM)
    new = body.interval_kwh.quantize(KWH_QUANTUM)
    if old == new:
        raise ApiError(422, "no_change", "the new value is the same as the stored value")
    session.add(m.ReadingRevision(reading_id=reading.id, old_interval_kwh=old, new_interval_kwh=new,
                                  reason=body.reason, user_id=actor.id))
    reading.interval_kwh = new
    session.commit()
    session.refresh(reading)
    return reading


@router.get("/readings/{reading_id}/revisions", response_model=list[RevisionOut], dependencies=[Depends(require("readings:read"))])
def list_revisions(reading_id: int, session: Session = Depends(get_session)):
    if session.get(m.EnergyReading, reading_id) is None:
        raise ApiError(404, "reading_not_found", f"reading {reading_id} does not exist")
    return session.scalars(
        select(m.ReadingRevision).where(m.ReadingRevision.reading_id == reading_id).order_by(m.ReadingRevision.id)
    ).all()


def _aware(value: datetime, field: str) -> datetime:
    try:
        return require_aware(value, field)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc))  # shared helper, mapped to the API error shape
