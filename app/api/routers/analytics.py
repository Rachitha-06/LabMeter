from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth_deps import require
from app.api.deps import get_session
from app.api.errors import ApiError
from app.services.analytics import consumption_buckets
from app.utils.time import require_aware

router = APIRouter(prefix="/analytics", tags=["analytics"])
MAX_WINDOW_DAYS = 400


@router.get("/consumption", dependencies=[Depends(require("analytics:read"))])
def consumption(
    start: datetime,
    end: datetime,
    granularity: Literal["day", "week", "month"] = "day",
    lab_id: Optional[int] = None,
    reading_type: Optional[Literal["measured", "imported", "simulated"]] = None,
    session: Session = Depends(get_session),
):
    try:
        start_utc = require_aware(start, "start")
        end_utc = require_aware(end, "end")
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc))
    if end_utc <= start_utc:
        raise ApiError(422, "validation_error", "end must be after start")
    if (end_utc - start_utc).days > MAX_WINDOW_DAYS:
        raise ApiError(422, "window_too_large", f"window must be at most {MAX_WINDOW_DAYS} days")
    buckets = consumption_buckets(
        session, start=start_utc, end=end_utc, granularity=granularity,
        lab_id=lab_id, reading_type=reading_type,
    )
    return {
        "granularity": granularity,
        "period_timezone": "each laboratory's local timezone",
        "note": "Energy is split by reading_type. Simulated values are not measured consumption.",
        "buckets": buckets,
    }
