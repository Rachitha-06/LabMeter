from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth_deps import bearer_token, current_user, require
from app.api.deps import get_session
from app.api.errors import ApiError
from app.api.responses import MeOut, SessionOut, UserOut
from app.auth.passwords import DUMMY_HASH, hash_password, verify_password
from app.auth.permissions import permissions_for
from app.auth.sessions import create_session, revoke_session, revoke_user_sessions
from app.config import (
    LOGIN_MAX_ATTEMPTS_PER_EMAIL, LOGIN_MAX_ATTEMPTS_PER_IP, SESSION_HOURS,
)
from app.db import models as m
from app.validation.schemas import LoginIn, UserCreate, UserPatch

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: m.User) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, request: Request, session: Session = Depends(get_session)):
    limiter = request.app.state.login_limiter
    ip = request.client.host if request.client else "unknown"
    email_key, ip_key = f"email:{body.email}", f"ip:{ip}"

    for key, limit in ((email_key, LOGIN_MAX_ATTEMPTS_PER_EMAIL), (ip_key, LOGIN_MAX_ATTEMPTS_PER_IP)):
        wait = limiter.retry_after(key, limit)
        if wait is not None:
            raise ApiError(429, "too_many_attempts", "too many failed sign-in attempts; try again later",
                           details={"retry_after_seconds": wait})

    user = session.scalar(select(m.User).where(m.User.email == body.email))
    # Always run one hash check, so unknown emails cannot be detected by timing.
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        limiter.record_failure(email_key)
        limiter.record_failure(ip_key)
        raise ApiError(401, "invalid_credentials", "email or password is incorrect")

    limiter.clear(email_key)
    token, expires_at = create_session(session, user, SESSION_HOURS)
    session.commit()
    return {"token": token, "expires_at": expires_at, "user": _user_out(user),
            "permissions": permissions_for(user.role)}


@router.post("/logout", status_code=204)
def logout(request: Request, _: m.User = Depends(current_user), session: Session = Depends(get_session)):
    revoke_session(session, bearer_token(request) or "")
    session.commit()
    return Response(status_code=204)


@router.get("/me", response_model=MeOut)
def me(user: m.User = Depends(current_user)):
    return {"user": _user_out(user), "permissions": permissions_for(user.role)}


@router.get("/users", response_model=list[UserOut])
def list_users(_: m.User = Depends(require("users:manage")), session: Session = Depends(get_session)):
    return session.scalars(select(m.User).order_by(m.User.email)).all()


@router.post("/users", status_code=201, response_model=UserOut)
def create_user(body: UserCreate, _: m.User = Depends(require("users:manage")), session: Session = Depends(get_session)):
    user = m.User(email=body.email, password_hash=hash_password(body.password), role=body.role, is_active=True)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError(409, "email_exists", "a user with this email already exists")
    session.refresh(user)
    return _user_out(user)


def _active_admin_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(m.User).where(
        m.User.role == "admin", m.User.is_active.is_(True)
    )) or 0


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserPatch, actor: m.User = Depends(require("users:manage")),
                session: Session = Depends(get_session)):
    target = session.get(m.User, user_id)
    if target is None:
        raise ApiError(404, "user_not_found", f"user {user_id} does not exist")

    changes = body.model_dump(exclude_unset=True)
    new_role = changes.get("role", target.role)
    new_active = changes.get("is_active", target.is_active)
    losing_admin = target.role == "admin" and target.is_active and (new_role != "admin" or not new_active)

    if losing_admin and _active_admin_count(session) <= 1:
        raise ApiError(409, "last_admin", "at least one active admin must remain")
    if target.id == actor.id and losing_admin:
        raise ApiError(409, "self_lockout", "you cannot remove your own admin access")

    if "role" in changes:
        target.role = changes["role"]
    if "is_active" in changes:
        target.is_active = changes["is_active"]
    if "password" in changes:
        target.password_hash = hash_password(changes["password"])
    if not new_active or "password" in changes or ("role" in changes and changes["role"] != target.role):
        revoke_user_sessions(session, target.id)
    session.commit()
    session.refresh(target)
    return _user_out(target)
