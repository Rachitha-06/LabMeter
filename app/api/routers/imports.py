from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.auth_deps import require
from app.api.deps import get_session
from app.api.errors import ApiError
from app.api.responses import BatchOut
from app.config import MAX_IMPORT_ROWS
from app.db import models as m
from app.services.readings_store import ImportFormatError, import_readings_csv

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/readings", dependencies=[Depends(require("imports:write"))])
def import_readings(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="Validate and report without writing anything"),
    interval_minutes: int = Query(60, ge=1, le=1440, description="Expected spacing of readings in minutes"),
    actor: m.User = Depends(require("imports:write")),
    session: Session = Depends(get_session),
):
    limit = request.app.state.max_import_bytes
    content = file.file.read(limit + 1)
    if len(content) > limit:
        raise ApiError(413, "file_too_large", f"file exceeds the {limit}-byte limit")
    try:
        result = import_readings_csv(
            session,
            content,
            filename=file.filename or "upload.csv",
            dry_run=dry_run,
            interval_minutes=interval_minutes,
            max_rows=MAX_IMPORT_ROWS,
            created_by=actor.id,
        )
    except ImportFormatError as exc:
        session.rollback()
        raise ApiError(422, "invalid_file", str(exc))
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return result


@router.get("/{batch_id}", response_model=BatchOut, dependencies=[Depends(require("imports:read"))])
def get_batch(batch_id: int, session: Session = Depends(get_session)):
    batch = session.get(m.ImportBatch, batch_id)
    if batch is None:
        raise ApiError(404, "batch_not_found", f"import batch {batch_id} does not exist")
    return batch
