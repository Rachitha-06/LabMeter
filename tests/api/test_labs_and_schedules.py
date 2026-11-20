from tests.api.helpers import lab_payload


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_create_and_fetch_lab(client):
    created = client.post("/api/labs", json=lab_payload())
    assert created.status_code == 201
    lab = created.json()
    assert lab["name"] == "Lab A" and lab["timezone"] == "Asia/Kolkata"
    assert client.get(f"/api/labs/{lab['id']}").json()["name"] == "Lab A"


def test_duplicate_lab_name_is_conflict(client):
    client.post("/api/labs", json=lab_payload())
    response = client.post("/api/labs", json=lab_payload())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "lab_exists"


def test_invalid_lab_is_rejected_with_structured_error(client):
    response = client.post("/api/labs", json=lab_payload(timezone="Mars/Olympus"))
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"]


def test_unknown_lab_returns_404_envelope(client):
    response = client.get("/api/labs/9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lab_not_found"


def test_patch_updates_only_given_fields(client, make_lab):
    lab_id = make_lab()
    response = client.patch(f"/api/labs/{lab_id}", json={"computer_count": 45})
    assert response.status_code == 200
    assert response.json()["computer_count"] == 45
    assert response.json()["name"] == "Lab A"


def test_patch_rejects_bad_timezone_and_unknown_fields(client, make_lab):
    lab_id = make_lab()
    assert client.patch(f"/api/labs/{lab_id}", json={"timezone": "Nowhere/City"}).status_code == 422
    assert client.patch(f"/api/labs/{lab_id}", json={"rogue": 1}).status_code == 422


def test_list_labs(client, make_lab):
    make_lab("Lab B")
    make_lab("Lab A")
    names = [lab["name"] for lab in client.get("/api/labs").json()]
    assert names == ["Lab A", "Lab B"]


def test_equipment_round_trip(client, make_lab):
    lab_id = make_lab()
    created = client.post(f"/api/labs/{lab_id}/equipment",
                          json={"equipment_type": "projector", "quantity": 2, "rated_power_w": 250})
    assert created.status_code == 201
    assert client.get(f"/api/labs/{lab_id}/equipment").json()[0]["equipment_type"] == "projector"


def test_equipment_rejects_non_positive_power(client, make_lab):
    lab_id = make_lab()
    response = client.post(f"/api/labs/{lab_id}/equipment",
                           json={"equipment_type": "fan", "rated_power_w": 0})
    assert response.status_code == 422


def test_schedule_round_trip(client, make_lab):
    lab_id = make_lab()
    body = {"weekday": 0, "open_time": "08:00:00", "close_time": "20:00:00", "valid_from": "2026-07-01"}
    assert client.post(f"/api/labs/{lab_id}/schedules", json=body).status_code == 201
    schedules = client.get(f"/api/labs/{lab_id}/schedules").json()
    assert len(schedules) == 1 and schedules[0]["weekday"] == 0


def test_overlapping_schedule_for_same_weekday_is_conflict(client, make_lab):
    lab_id = make_lab()
    first = {"weekday": 0, "open_time": "08:00:00", "close_time": "20:00:00",
             "valid_from": "2026-07-01", "valid_to": "2026-08-31"}
    client.post(f"/api/labs/{lab_id}/schedules", json=first)
    overlapping = {"weekday": 0, "open_time": "09:00:00", "close_time": "17:00:00", "valid_from": "2026-08-31"}
    response = client.post(f"/api/labs/{lab_id}/schedules", json=overlapping)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "schedule_overlap"


def test_non_overlapping_schedule_for_same_weekday_is_allowed(client, make_lab):
    lab_id = make_lab()
    first = {"weekday": 0, "open_time": "08:00:00", "close_time": "20:00:00",
             "valid_from": "2026-07-01", "valid_to": "2026-08-31"}
    client.post(f"/api/labs/{lab_id}/schedules", json=first)
    later = {"weekday": 0, "open_time": "09:00:00", "close_time": "17:00:00", "valid_from": "2026-09-01"}
    assert client.post(f"/api/labs/{lab_id}/schedules", json=later).status_code == 201


def test_overnight_schedule_is_rejected(client, make_lab):
    lab_id = make_lab()
    body = {"weekday": 0, "open_time": "22:00:00", "close_time": "02:00:00", "valid_from": "2026-07-01"}
    assert client.post(f"/api/labs/{lab_id}/schedules", json=body).status_code == 422
