def reading_body(lab_id, **overrides):
    body = {
        "lab_id": lab_id,
        "timestamp": "2026-10-01T08:00:00+05:30",
        "value": "1.25",
        "reading_type": "measured",
        "source": "meter-export",
    }
    body.update(overrides)
    return body


def test_create_reading_returns_utc_timestamp(client, make_lab):
    lab_id = make_lab()
    response = client.post("/api/readings", json=reading_body(lab_id))
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "created"
    assert payload["reading"]["timestamp_utc"].startswith("2026-10-01T02:30:00")


def test_identical_repeat_is_reported_as_duplicate_not_written(client, make_lab):
    lab_id = make_lab()
    first = client.post("/api/readings", json=reading_body(lab_id)).json()["reading"]
    again = client.post("/api/readings", json=reading_body(lab_id))
    assert again.status_code == 200
    assert again.json()["status"] == "duplicate"
    assert again.json()["reading"]["id"] == first["id"]
    assert len(client.get("/api/readings").json()) == 1


def test_different_value_for_same_reading_is_conflict_and_nothing_is_overwritten(client, make_lab):
    lab_id = make_lab()
    first = client.post("/api/readings", json=reading_body(lab_id)).json()["reading"]
    response = client.post("/api/readings", json=reading_body(lab_id, value="9.99"))
    assert response.status_code == 409
    details = response.json()["error"]["details"]
    assert details["existing_reading_id"] == first["id"]
    assert details["existing_interval_kwh"] == "1.2500"
    stored = client.get(f"/api/readings/{first['id']}").json()
    assert stored["interval_kwh"] == "1.2500"


def test_same_time_on_another_meter_is_allowed(client, make_lab):
    lab_id = make_lab()
    client.post("/api/readings", json=reading_body(lab_id, meter_id="A"))
    response = client.post("/api/readings", json=reading_body(lab_id, meter_id="B", value="2.0"))
    assert response.status_code == 201


def test_reading_for_unknown_lab_is_404(client):
    response = client.post("/api/readings", json=reading_body(999))
    assert response.status_code == 404


def test_negative_and_naive_readings_are_rejected(client, make_lab):
    lab_id = make_lab()
    assert client.post("/api/readings", json=reading_body(lab_id, value="-1")).status_code == 422
    assert client.post("/api/readings", json=reading_body(lab_id, timestamp="2026-10-01T08:00:00")).status_code == 422


def test_list_filters_by_lab_and_paginates(client, make_lab):
    lab_id = make_lab()
    for hour in range(5):
        client.post("/api/readings", json=reading_body(lab_id, timestamp=f"2026-10-01T0{hour}:00:00+00:00"))
    page = client.get(f"/api/readings?lab_id={lab_id}&limit=2&offset=2").json()
    assert len(page) == 2
    assert page[0]["timestamp_utc"].startswith("2026-10-01T02:00:00")


def test_list_rejects_naive_date_filter(client):
    assert client.get("/api/readings?start=2026-10-01T00:00:00").status_code == 422


def test_list_limit_is_bounded(client):
    assert client.get("/api/readings?limit=5000").status_code == 422


def test_correction_keeps_the_original_value_in_revisions(client, make_lab):
    lab_id = make_lab()
    reading = client.post("/api/readings", json=reading_body(lab_id)).json()["reading"]
    response = client.patch(f"/api/readings/{reading['id']}",
                            json={"interval_kwh": "2.0", "reason": "meter was reading double"})
    assert response.status_code == 200
    assert response.json()["interval_kwh"] == "2.0000"
    revisions = client.get(f"/api/readings/{reading['id']}/revisions").json()
    assert len(revisions) == 1
    assert revisions[0]["old_interval_kwh"] == "1.2500"
    assert revisions[0]["new_interval_kwh"] == "2.0000"
    assert revisions[0]["reason"] == "meter was reading double"


def test_correction_requires_a_real_reason(client, make_lab):
    lab_id = make_lab()
    reading = client.post("/api/readings", json=reading_body(lab_id)).json()["reading"]
    response = client.patch(f"/api/readings/{reading['id']}", json={"interval_kwh": "2.0", "reason": "no"})
    assert response.status_code == 422


def test_correction_cannot_change_reading_type_or_source(client, make_lab):
    lab_id = make_lab()
    reading = client.post("/api/readings", json=reading_body(lab_id)).json()["reading"]
    response = client.patch(f"/api/readings/{reading['id']}",
                            json={"interval_kwh": "2.0", "reason": "fix", "reading_type": "measured"})
    assert response.status_code == 422


def test_correction_with_same_value_is_refused(client, make_lab):
    lab_id = make_lab()
    reading = client.post("/api/readings", json=reading_body(lab_id)).json()["reading"]
    response = client.patch(f"/api/readings/{reading['id']}",
                            json={"interval_kwh": "1.25", "reason": "checked, no change"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_change"


def test_correction_of_missing_reading_is_404(client):
    response = client.patch("/api/readings/9999", json={"interval_kwh": "1", "reason": "missing row"})
    assert response.status_code == 404
