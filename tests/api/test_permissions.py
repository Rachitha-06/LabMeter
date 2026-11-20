import pytest

from tests.api.helpers import lab_payload

ROLES = ["admin", "lab_manager", "staff", "evaluator"]


def assert_allowed(response, allowed):
    if allowed:
        assert response.status_code < 400, response.text
    else:
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("role", ROLES)
def test_creating_a_laboratory(role_client, role):
    allowed = role in {"admin", "lab_manager"}
    response = role_client(role).post("/api/labs", json=lab_payload(name=f"Lab for {role}"))
    assert_allowed(response, allowed)


@pytest.mark.parametrize("role", ROLES)
def test_reading_laboratories_is_open_to_everyone(role_client, make_lab, role):
    make_lab()
    assert role_client(role).get("/api/labs").status_code == 200


@pytest.mark.parametrize("role", ROLES)
def test_entering_a_reading(role_client, make_lab, role):
    lab_id = make_lab()
    response = role_client(role).post("/api/readings", json={
        "lab_id": lab_id, "timestamp": "2026-10-01T00:00:00Z", "value": "1.0",
        "reading_type": "measured", "source": "test"})
    assert_allowed(response, role != "evaluator")


@pytest.mark.parametrize("role", ROLES)
def test_correcting_a_reading(client, role_client, make_lab, role):
    lab_id = make_lab()
    reading = client.post("/api/readings", json={
        "lab_id": lab_id, "timestamp": "2026-10-01T00:00:00Z", "value": "1.0",
        "reading_type": "measured", "source": "test"}).json()["reading"]
    response = role_client(role).patch(f"/api/readings/{reading['id']}",
                                       json={"interval_kwh": "2.0", "reason": "checked against the meter"})
    assert_allowed(response, role in {"admin", "lab_manager"})


@pytest.mark.parametrize("role", ROLES)
def test_importing_a_file(role_client, role):
    content = b"lab_name,timestamp,value,reading_type\n"
    response = role_client(role).post("/api/imports/readings?dry_run=true",
                                      files={"file": ("r.csv", content, "text/csv")})
    assert_allowed(response, role != "evaluator")


@pytest.mark.parametrize("role", ROLES)
def test_analytics_is_open_to_everyone(role_client, role):
    response = role_client(role).get("/api/analytics/consumption?start=2026-10-01T00:00:00Z&end=2026-10-02T00:00:00Z")
    assert response.status_code == 200


@pytest.mark.parametrize("role", ROLES)
def test_user_management_is_admin_only(role_client, role):
    response = role_client(role).get("/api/auth/users")
    assert_allowed(response, role == "admin")


def test_forbidden_response_names_the_missing_permission(role_client):
    response = role_client("evaluator").post("/api/labs", json=lab_payload())
    assert response.json()["error"]["details"]["required"] == "labs:write"


def test_correction_records_who_made_it(client, role_client, make_lab):
    lab_id = make_lab()
    reading = client.post("/api/readings", json={
        "lab_id": lab_id, "timestamp": "2026-10-01T00:00:00Z", "value": "1.0",
        "reading_type": "measured", "source": "test"}).json()["reading"]
    manager = role_client("lab_manager")
    manager_id = manager.get("/api/auth/me").json()["user"]["id"]
    manager.patch(f"/api/readings/{reading['id']}", json={"interval_kwh": "2.0", "reason": "checked against the meter"})
    revisions = client.get(f"/api/readings/{reading['id']}/revisions").json()
    assert revisions[0]["user_id"] == manager_id


def test_import_batch_records_its_owner(client, role_client, make_lab):
    make_lab("Lab A")
    staff = role_client("staff")
    staff_id = staff.get("/api/auth/me").json()["user"]["id"]
    result = staff.post("/api/imports/readings", files={"file": (
        "r.csv", b"lab_name,timestamp,value,reading_type\nLab A,2026-10-01T00:00:00Z,1.0,measured\n", "text/csv")}).json()
    assert client.get(f"/api/imports/{result['batch_id']}").json()["created_by"] == staff_id
