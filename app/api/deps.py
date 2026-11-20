from typing import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db import models as m


def get_session(request: Request) -> Iterator[Session]:
    """One session per request. Routes commit explicitly; anything uncommitted is rolled back on close."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def lab_or_404(session: Session, lab_id: int) -> m.Laboratory:
    lab = session.get(m.Laboratory, lab_id)
    if lab is None:
        raise ApiError(404, "lab_not_found", f"laboratory {lab_id} does not exist")
    return lab
