"""Schedule rules that need the database."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import models as m


def find_overlapping_schedule(
    session: Session, lab_id: int, weekday: int, valid_from: date, valid_to: Optional[date]
) -> Optional[m.OperatingSchedule]:
    """Return an existing schedule for the same lab and weekday whose validity dates overlap.

    Validity ranges are inclusive. A missing valid_to means open-ended.
    """
    conditions = [
        m.OperatingSchedule.lab_id == lab_id,
        m.OperatingSchedule.weekday == weekday,
        or_(m.OperatingSchedule.valid_to.is_(None), m.OperatingSchedule.valid_to >= valid_from),
    ]
    if valid_to is not None:
        conditions.append(m.OperatingSchedule.valid_from <= valid_to)
    return session.scalar(select(m.OperatingSchedule).where(*conditions).limit(1))
