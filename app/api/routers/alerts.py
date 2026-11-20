from __future__ import annotations

from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_deps import require
from app.api.deps import get_session
from app.api.errors import ApiError
from app.api.responses import ReviewOut
from app.db import models as m
from app.services.alerts import InvalidTransition, add_comment, detect_alerts, transition
from app.utils.time import as_utc
from app.validation.schemas import AlertCommentIn, AlertStatusIn, DetectIn

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _describe(alert: m.Alert, lab: m.Laboratory) -> dict:
    tz = ZoneInfo(lab.timezone)
    start = as_utc(alert.period_start).astimezone(tz)
    end = as_utc(alert.period_end).astimezone(tz)
    actual = float(alert.actual_kwh)
    expected = float(alert.expected_kwh) if alert.expected_kwh is not None else None
    return {
        "id": alert.id,
        "lab_id": alert.lab_id,
        "lab_name": lab.name,
        "period_start": as_utc(alert.period_start).isoformat(),
        "period_end": as_utc(alert.period_end).isoformat(),
        "period_local": f"{start:%a %d %b %Y, %H:%M}–{end:%H:%M} ({lab.timezone})",
        "actual_kwh": f"{alert.actual_kwh}",
        "expected_kwh": None if expected is None else f"{alert.expected_kwh}",
        "difference_kwh": None if expected is None else f"{actual - expected:.4f}",
        "rule_id": alert.rule_id,
        "severity": alert.severity,
        "severity_meaning": "review priority from the size of the excess; not a confidence score",
        "status": alert.status,
        "explanation": alert.explanation,
        "created_at": as_utc(alert.created_at).isoformat() if alert.created_at else None,
    }


def _alert_or_404(session: Session, alert_id: int) -> tuple[m.Alert, m.Laboratory]:
    alert = session.get(m.Alert, alert_id)
    if alert is None:
        raise ApiError(404, "alert_not_found", f"alert {alert_id} does not exist")
    return alert, session.get(m.Laboratory, alert.lab_id)


@router.post("/detect", dependencies=[Depends(require("alerts:detect"))])
def run_detection(body: DetectIn, session: Session = Depends(get_session)):
    if body.lab_id is not None and session.get(m.Laboratory, body.lab_id) is None:
        raise ApiError(404, "lab_not_found", f"laboratory {body.lab_id} does not exist")
    return detect_alerts(session, lab_id=body.lab_id, start=body.start, end=body.end)


@router.get("", dependencies=[Depends(require("alerts:read"))])
def list_alerts(lab_id: Optional[int] = None, status: Optional[str] = Query(None, pattern="^(open|under_review|resolved)$"),
                limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                session: Session = Depends(get_session)):
    query = select(m.Alert)
    if lab_id is not None:
        query = query.where(m.Alert.lab_id == lab_id)
    if status is not None:
        query = query.where(m.Alert.status == status)
    alerts = session.scalars(query.order_by(m.Alert.period_start.desc(), m.Alert.id.desc())
                             .limit(limit).offset(offset)).all()
    labs = {lab.id: lab for lab in session.scalars(select(m.Laboratory)).all()}
    return [_describe(a, labs[a.lab_id]) for a in alerts]


@router.get("/count", dependencies=[Depends(require("alerts:read"))])
def count_alerts(lab_id: Optional[int] = None,
                 status: Optional[str] = Query(None, pattern="^(open|under_review|resolved)$"),
                 session: Session = Depends(get_session)):
    query = select(func.count()).select_from(m.Alert)
    if lab_id is not None:
        query = query.where(m.Alert.lab_id == lab_id)
    if status is not None:
        query = query.where(m.Alert.status == status)
    return {"total": session.scalar(query)}


@router.get("/{alert_id}", dependencies=[Depends(require("alerts:read"))])
def get_alert(alert_id: int, session: Session = Depends(get_session)):
    alert, lab = _alert_or_404(session, alert_id)
    reviews = session.scalars(select(m.AlertReview).where(m.AlertReview.alert_id == alert_id)
                              .order_by(m.AlertReview.id)).all()
    return {**_describe(alert, lab), "reviews": [ReviewOut.model_validate(r).model_dump() for r in reviews]}


@router.patch("/{alert_id}", dependencies=[Depends(require("alerts:review"))])
def update_status(alert_id: int, body: AlertStatusIn, actor: m.User = Depends(require("alerts:review")),
                  session: Session = Depends(get_session)):
    alert, lab = _alert_or_404(session, alert_id)
    try:
        transition(session, alert, body.status, body.comment, actor.id)
    except InvalidTransition as exc:
        raise ApiError(409, "invalid_transition", str(exc))
    session.refresh(alert)
    return _describe(alert, lab)


@router.post("/{alert_id}/comments", status_code=201, response_model=ReviewOut,
             dependencies=[Depends(require("alerts:review"))])
def comment(alert_id: int, body: AlertCommentIn, actor: m.User = Depends(require("alerts:review")),
            session: Session = Depends(get_session)):
    alert, _ = _alert_or_404(session, alert_id)
    return add_comment(session, alert, body.comment, actor.id)
