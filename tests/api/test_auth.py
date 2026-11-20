from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import _digest
from app.db import models as m
from app.db.session import make_session_factory
from tests.api.conftest import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.api.helpers import add_user, sign_in


def test_password_hashing_is_salted_and_verifiable():
    first, second = hash_password("correct horse battery"), hash_password("correct horse battery")
    assert first != second and first.startswith("scrypt$")
    assert verify_password("correct horse battery", first)
    assert not verify_password("wrong password", first)
    assert not verify_password("anything", "not-a-hash")


def test_login_returns_token_user_and_permissions(anon):
    response = anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token"] and body["user"]["role"] == "admin"
    assert "users:manage" in body["permissions"]


def test_me_reports_the_signed_in_user(client):
    body = client.get("/api/auth/me").json()
    assert body["user"]["email"] == ADMIN_EMAIL
    assert "labs:write" in body["permissions"]


def test_email_is_case_insensitive_at_login(anon):
    assert anon.post("/api/auth/login", json={"email": "ADMIN@Example.test", "password": ADMIN_PASSWORD}).status_code == 200


def test_wrong_password_and_unknown_email_give_the_same_answer(anon):
    wrong = anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "nope-nope-nope"})
    unknown = anon.post("/api/auth/login", json={"email": "nobody@example.test", "password": "nope-nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"] == unknown.json()["error"]
    assert wrong.json()["error"]["code"] == "invalid_credentials"


def test_protected_endpoints_require_a_token(anon):
    assert anon.get("/api/labs").status_code == 401
    assert anon.post("/api/readings", json={}).status_code == 401
    assert anon.get("/api/analytics/consumption?start=2026-10-01T00:00:00Z&end=2026-10-02T00:00:00Z").status_code == 401
    assert anon.get("/api/labs").json()["error"]["code"] == "unauthorized"


def test_health_stays_public(anon):
    assert anon.get("/api/health").status_code == 200


def test_invalid_token_is_rejected(anon):
    anon.headers["Authorization"] = "Bearer not-a-real-token"
    assert anon.get("/api/labs").status_code == 401


def test_logout_revokes_the_token(client):
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client, engine):
    with make_session_factory(engine)() as session:
        session.execute(update(m.AuthSession).values(expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
        session.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_session_lifetime_is_limited(client, engine):
    with make_session_factory(engine)() as session:
        row = session.scalar(select(m.AuthSession))
        assert row is not None
        assert row.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(hours=11)


def test_only_a_hash_of_the_token_is_stored(client, engine):
    token = client.headers["Authorization"].split(" ", 1)[1]
    with make_session_factory(engine)() as session:
        stored = [row.token_hash for row in session.scalars(select(m.AuthSession))]
    assert _digest(token) in stored
    assert token not in stored


def test_passwords_are_never_stored_in_plain_text(client, engine):
    with make_session_factory(engine)() as session:
        user = session.scalar(select(m.User).where(m.User.email == ADMIN_EMAIL))
    assert user.password_hash != ADMIN_PASSWORD
    assert verify_password(ADMIN_PASSWORD, user.password_hash)


def test_repeated_wrong_passwords_lock_the_account_temporarily(anon):
    for _ in range(5):
        assert anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-wrong-wrong"}).status_code == 401
    locked = anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "too_many_attempts"
    assert locked.json()["error"]["details"]["retry_after_seconds"] > 0


def test_successful_login_resets_the_failure_count(anon):
    for _ in range(4):
        anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-wrong-wrong"})
    assert anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200
    for _ in range(4):
        assert anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-wrong-wrong"}).status_code == 401


def test_deactivated_user_loses_access_and_cannot_sign_in(client, anon, engine):
    add_user(engine, "temp@example.test", "temporary-password-1", "staff")
    temp = anon.__class__(anon.app)
    temp.__enter__()
    try:
        token = sign_in(temp, "temp@example.test", "temporary-password-1")
        temp.headers["Authorization"] = f"Bearer {token}"
        assert temp.get("/api/auth/me").status_code == 200
        users = client.get("/api/auth/users").json()
        target = next(u for u in users if u["email"] == "temp@example.test")
        assert client.patch(f"/api/auth/users/{target['id']}", json={"is_active": False}).status_code == 200
        assert temp.get("/api/auth/me").status_code == 401
        assert temp.post("/api/auth/login", json={"email": "temp@example.test",
                                                    "password": "temporary-password-1"}).status_code == 401
    finally:
        temp.__exit__(None, None, None)


def test_changing_a_password_signs_the_user_out_everywhere(client, anon, engine):
    add_user(engine, "rotate@example.test", "first-password-1", "staff")
    token = sign_in(anon, "rotate@example.test", "first-password-1")
    target = next(u for u in client.get("/api/auth/users").json() if u["email"] == "rotate@example.test")
    assert client.patch(f"/api/auth/users/{target['id']}", json={"password": "second-password-2"}).status_code == 200
    anon.headers["Authorization"] = f"Bearer {token}"
    assert anon.get("/api/auth/me").status_code == 401


def test_admin_can_create_a_user(client):
    response = client.post("/api/auth/users", json={
        "email": "New.Person@example.test", "password": "a-long-password-1", "role": "evaluator"})
    assert response.status_code == 201
    assert response.json()["email"] == "new.person@example.test"


def test_duplicate_email_is_rejected(client):
    body = {"email": "dup@example.test", "password": "a-long-password-1", "role": "staff"}
    assert client.post("/api/auth/users", json=body).status_code == 201
    response = client.post("/api/auth/users", json=body)
    assert response.status_code == 409 and response.json()["error"]["code"] == "email_exists"


def test_weak_password_role_and_email_are_rejected(client):
    assert client.post("/api/auth/users", json={"email": "a@example.test", "password": "short",
                                                "role": "staff"}).status_code == 422
    assert client.post("/api/auth/users", json={"email": "a@example.test", "password": "a-long-password-1",
                                                "role": "superuser"}).status_code == 422
    assert client.post("/api/auth/users", json={"email": "not-an-email", "password": "a-long-password-1",
                                                "role": "staff"}).status_code == 422


def test_last_active_admin_cannot_be_demoted(client):
    me = client.get("/api/auth/me").json()["user"]
    response = client.patch(f"/api/auth/users/{me['id']}", json={"role": "staff"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_admin"


def test_admin_cannot_remove_their_own_access_when_another_admin_exists(client, engine):
    add_user(engine, "second@example.test", "second-admin-pass-1", "admin")
    me = client.get("/api/auth/me").json()["user"]
    response = client.patch(f"/api/auth/users/{me['id']}", json={"role": "staff"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "self_lockout"


def test_one_admin_can_demote_another(client, engine):
    add_user(engine, "second@example.test", "second-admin-pass-1", "admin")
    other = next(u for u in client.get("/api/auth/users").json() if u["email"] == "second@example.test")
    assert client.patch(f"/api/auth/users/{other['id']}", json={"role": "evaluator"}).status_code == 200


def test_unknown_user_id_is_404(client):
    assert client.patch("/api/auth/users/9999", json={"is_active": False}).status_code == 404
