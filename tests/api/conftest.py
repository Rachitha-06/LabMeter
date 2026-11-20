import os

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import make_engine, make_session_factory
from app.main import create_app
from tests.api.helpers import add_user, sign_in

ADMIN_EMAIL = "admin@example.test"
ADMIN_PASSWORD = "test-only-admin-passphrase"
ROLE_PASSWORD = "test-only-role-passphrase"


@pytest.fixture()
def engine(tmp_path):
    """SQLite by default. Set TEST_DATABASE_URL to run the same tests against PostgreSQL (the schema is recreated)."""
    external = os.environ.get("TEST_DATABASE_URL")
    if external:
        engine = make_engine(external)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        yield engine
        Base.metadata.drop_all(engine)
        engine.dispose()
        return
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def app(engine):
    add_user(engine, ADMIN_EMAIL, ADMIN_PASSWORD, "admin")
    return create_app(session_factory=make_session_factory(engine), max_import_bytes=2_000_000)


@pytest.fixture()
def client(app):
    """Signed-in administrator."""
    with TestClient(app) as test_client:
        test_client.headers["Authorization"] = f"Bearer {sign_in(test_client, ADMIN_EMAIL, ADMIN_PASSWORD)}"
        yield test_client


@pytest.fixture()
def anon(app):
    """Not signed in."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def role_client(app, engine):
    """Factory returning a signed-in client for a user with the given role."""
    opened = []

    def _make(role):
        if role == "admin":
            email, password = ADMIN_EMAIL, ADMIN_PASSWORD  # the admin account already exists
        else:
            email, password = f"{role}@example.test", ROLE_PASSWORD
            add_user(engine, email, password, role)
        test_client = TestClient(app)
        test_client.__enter__()
        opened.append(test_client)
        test_client.headers["Authorization"] = f"Bearer {sign_in(test_client, email, password)}"
        return test_client

    yield _make
    for test_client in opened:
        test_client.__exit__(None, None, None)


@pytest.fixture()
def make_lab(client):
    def _make(name="Lab A", timezone="Asia/Kolkata", computer_count=30):
        response = client.post("/api/labs", json={
            "name": name, "building": "Block A", "lab_type": "Teaching",
            "computer_count": computer_count, "timezone": timezone,
        })
        assert response.status_code == 201, response.text
        return response.json()["id"]
    return _make
