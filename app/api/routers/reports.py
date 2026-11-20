from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_deps import require
from app.api.deps import get_session
from app.api.errors import ApiError
from app.db import models as m
from app.services.reports import build_energy_report, report_csv
from app.utils.time import require_aware

router = APIRouter(prefix="/reports", tags=["reports"])
MAX_WINDOW_DAYS = 400


@router.get("/energy", dependencies=[Depends(require("reports:read"))])
def energy_report(
    start: datetime,
    end: datetime,
    lab_id: Optional[int] = None,
    format: str = Query("json", pattern="^(json|csv)$"),
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

    if lab_id is not None:
        lab_ids = [lab_id] if session.get(m.Laboratory, lab_id) is not None else []
        if not lab_ids:
            raise ApiError(404, "lab_not_found", f"laboratory {lab_id} does not exist")
    else:
        lab_ids = [lab.id for lab in session.scalars(select(m.Laboratory)).all()]

    report = build_energy_report(session, lab_ids, start_utc, end_utc)
    if format == "csv":
        filename = f"labmeter-energy-{start_utc:%Y%m%d}-{end_utc:%Y%m%d}.csv"
        return Response(content=report_csv(report), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    return report
