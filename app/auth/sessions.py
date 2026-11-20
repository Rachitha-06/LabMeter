"""Opaque bearer tokens stored as SHA-256 hashes. A database leak does not reveal usable tokens."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.utils.time import as_utc


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: m.User, hours: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
    db.add(m.AuthSession(user_id=user.id, token_hash=_digest(token), expires_at=expires_at))
    db.flush()
    return token, expires_at


def resolve_user(db: Session, token: Optional[str]) -> Optional[m.User]:
    if not token:
        return None
    row = db.scalar(select(m.AuthSession).where(m.AuthSession.token_hash == _digest(token)))
    if row is None or row.revoked_at is not None:
        return None
    if as_utc(row.expires_at) <= datetime.now(timezone.utc):
        return None
    user = db.get(m.User, row.user_id)
    if user is None or not user.is_active:
        return None
    return user


def revoke_session(db: Session, token: str) -> None:
    row = db.scalar(select(m.AuthSession).where(m.AuthSession.token_hash == _digest(token)))
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)


def revoke_user_sessions(db: Session, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    for row in db.scalars(select(m.AuthSession).where(
        m.AuthSession.user_id == user_id, m.AuthSession.revoked_at.is_(None)
    )):
        row.revoked_at = now
