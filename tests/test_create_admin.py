import create_admin
from sqlalchemy import select

from app.db import models as m
from app.db.base import Base
from app.db.session import make_engine, make_session_factory


def test_first_admin_is_created_from_environment_password(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'admin.db'}"
    engine = make_engine(db_url)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("LABMETER_ADMIN_PASSWORD", "bootstrap-password-1")

    assert create_admin.main(["--email", "Owner@Example.test", "--db-url", db_url]) == 0
    with make_session_factory(engine)() as session:
        user = session.scalar(select(m.User))
    assert user.email == "owner@example.test" and user.role == "admin" and user.is_active
    assert user.password_hash != "bootstrap-password-1"
    engine.dispose()


def test_duplicate_admin_email_is_refused(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'admin.db'}"
    engine = make_engine(db_url)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("LABMETER_ADMIN_PASSWORD", "bootstrap-password-1")
    assert create_admin.main(["--email", "owner@example.test", "--db-url", db_url]) == 0
    assert create_admin.main(["--email", "owner@example.test", "--db-url", db_url]) == 1
    engine.dispose()


def test_short_password_is_refused(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'admin.db'}"
    engine = make_engine(db_url)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("LABMETER_ADMIN_PASSWORD", "short")
    assert create_admin.main(["--email", "owner@example.test", "--db-url", db_url]) == 1
    engine.dispose()
