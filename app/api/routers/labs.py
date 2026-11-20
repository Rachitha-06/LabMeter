from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth_deps import require
from app.api.deps import get_session, lab_or_404
from app.api.errors import ApiError
from app.api.responses import EquipmentOut, LabOut, ScheduleOut
from app.db import models as m
from app.services.schedules import find_overlapping_schedule
from app.utils.time import as_utc
from app.validation.schemas import EquipmentIn, LabIn, LabPatch, ScheduleCreate

router = APIRouter(prefix="/labs", tags=["laboratories"])


@router.post("", status_code=201, response_model=LabOut, dependencies=[Depends(require("labs:write"))])
def create_lab(body: LabIn, session: Session = Depends(get_session)):
    lab = m.Laboratory(**body.model_dump())
    session.add(lab)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError(409, "lab_exists", f"a laboratory named '{body.name}' already exists")
    session.refresh(lab)
    return lab


@router.get("", response_model=list[LabOut], dependencies=[Depends(require("labs:read"))])
def list_labs(include_archived: bool = False, session: Session = Depends(get_session)):
    query = select(m.Laboratory).order_by(m.Laboratory.name)
    if not include_archived:
        query = query.where(m.Laboratory.archived_at.is_(None))
    return session.scalars(query).all()


@router.post("/{lab_id}/archive", response_model=LabOut, dependencies=[Depends(require("labs:write"))])
def archive_lab(lab_id: int, session: Session = Depends(get_session)):
    """Hide a laboratory from lists and refuse new readings. Its history is kept."""
    lab = lab_or_404(session, lab_id)
    lab.archived_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(lab)
    return lab


@router.post("/{lab_id}/restore", response_model=LabOut, dependencies=[Depends(require("labs:write"))])
def restore_lab(lab_id: int, session: Session = Depends(get_session)):
    lab = lab_or_404(session, lab_id)
    lab.archived_at = None
    session.commit()
    session.refresh(lab)
    return lab


@router.get("/{lab_id}/data-range", dependencies=[Depends(require("readings:read"))])
def data_range(lab_id: int, session: Session = Depends(get_session)):
    """First and last local day with readings, so the interface can default to a valid forecast date."""
    lab = lab_or_404(session, lab_id)
    first, last = session.execute(select(func.min(m.EnergyReading.timestamp_utc),
                                         func.max(m.EnergyReading.timestamp_utc))
                                  .where(m.EnergyReading.lab_id == lab_id)).one()
    if first is None:
        return {"timezone": lab.timezone, "first_day": None, "last_day": None}
    tz = ZoneInfo(lab.timezone)
    return {"timezone": lab.timezone,
            "first_day": as_utc(first).astimezone(tz).date().isoformat(),
            "last_day": as_utc(last).astimezone(tz).date().isoformat()}


@router.get("/{lab_id}", response_model=LabOut, dependencies=[Depends(require("labs:read"))])
def get_lab(lab_id: int, session: Session = Depends(get_session)):
    return lab_or_404(session, lab_id)


@router.patch("/{lab_id}", response_model=LabOut, dependencies=[Depends(require("labs:write"))])
def update_lab(lab_id: int, body: LabPatch, session: Session = Depends(get_session)):
    lab = lab_or_404(session, lab_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(lab, field, value)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError(409, "lab_exists", "another laboratory already uses that name")
    session.refresh(lab)
    return lab


@router.post("/{lab_id}/equipment", status_code=201, response_model=EquipmentOut, dependencies=[Depends(require("labs:write"))])
def add_equipment(lab_id: int, body: EquipmentIn, session: Session = Depends(get_session)):
    lab_or_404(session, lab_id)
    item = m.Equipment(lab_id=lab_id, **body.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/{lab_id}/equipment", response_model=list[EquipmentOut], dependencies=[Depends(require("labs:read"))])
def list_equipment(lab_id: int, session: Session = Depends(get_session)):
    lab_or_404(session, lab_id)
    return session.scalars(select(m.Equipment).where(m.Equipment.lab_id == lab_id)).all()


@router.post("/{lab_id}/schedules", status_code=201, response_model=ScheduleOut, dependencies=[Depends(require("labs:write"))])
def add_schedule(lab_id: int, body: ScheduleCreate, session: Session = Depends(get_session)):
    lab_or_404(session, lab_id)
    clash = find_overlapping_schedule(session, lab_id, body.weekday, body.valid_from, body.valid_to)
    if clash is not None:
        raise ApiError(
            409, "schedule_overlap",
            "this weekday already has a schedule whose validity dates overlap",
            details={"existing_schedule_id": clash.id},
        )
    item = m.OperatingSchedule(lab_id=lab_id, **body.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/{lab_id}/schedules", response_model=list[ScheduleOut], dependencies=[Depends(require("labs:read"))])
def list_schedules(lab_id: int, session: Session = Depends(get_session)):
    lab_or_404(session, lab_id)
    return session.scalars(
        select(m.OperatingSchedule)
        .where(m.OperatingSchedule.lab_id == lab_id)
        .order_by(m.OperatingSchedule.weekday, m.OperatingSchedule.valid_from)
    ).all()
