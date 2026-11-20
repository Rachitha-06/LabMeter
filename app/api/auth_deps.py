from __future__ import annotations

from typing import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.errors import ApiError
from app.auth.permissions import has_permission
from app.auth.sessions import resolve_user
from app.db import models as m


def bearer_token(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def current_user(request: Request, session: Session = Depends(get_session)) -> m.User:
    user = resolve_user(session, bearer_token(request))
    if user is None:
        raise ApiError(401, "unauthorized", "sign in to continue")
    return user


def require(permission: str) -> Callable[..., m.User]:
    def check(user: m.User = Depends(current_user)) -> m.User:
        if not has_permission(user.role, permission):
            raise ApiError(403, "forbidden", f"your role ({user.role}) cannot do this",
                           details={"required": permission})
        return user
    return check
