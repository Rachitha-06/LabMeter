from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_deps import require
from app.api.deps import get_session
from app.api.errors import ApiError
from app.db import models as m

router = APIRouter(prefix="/calendar", tags=["calendar"])
MAX_DAYS_PER_CALL = 400


class CalendarDayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    is_holiday: bool = False
    is_exam_period: bool = False
    is_semester: bool = True
    label: Optional[str] = Field(default=None, max_length=160)


class CalendarBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[CalendarDayIn] = Field(min_length=1, max_length=MAX_DAYS_PER_CALL)

    @model_validator(mode="after")
    def _unique_days(self) -> "CalendarBatchIn":
        seen = [d.day for d in self.days]
        if len(seen) != len(set(seen)):
            raise ValueError("each day may appear only once in a batch")
        return self


@router.get("", dependencies=[Depends(require("labs:read"))])
def list_calendar(start: date, end: date, session: Session = Depends(get_session)):
    if end < start:
        raise ApiError(422, "validation_error", "end must not be before start")
    rows = session.scalars(select(m.AcademicCalendarDay).where(
        m.AcademicCalendarDay.day >= start, m.AcademicCalendarDay.day <= end
    ).order_by(m.AcademicCalendarDay.day)).all()
    return [{"day": r.day.isoformat(), "is_holiday": r.is_holiday, "is_exam_period": r.is_exam_period,
             "is_semester": r.is_semester, "label": r.label} for r in rows]


@router.put("", dependencies=[Depends(require("calendar:write"))])
def upsert_calendar(body: CalendarBatchIn, session: Session = Depends(get_session)):
    """Create or replace calendar days. Holidays and exam periods drive the alert rule and the models."""
    created = updated = 0
    for item in body.days:
        row = session.get(m.AcademicCalendarDay, item.day)
        if row is None:
            session.add(m.AcademicCalendarDay(**item.model_dump()))
            created += 1
        else:
            for field, value in item.model_dump().items():
                setattr(row, field, value)
            updated += 1
    session.commit()
    return {"created": created, "updated": updated}
