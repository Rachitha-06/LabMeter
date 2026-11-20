"""Tests for the features added while fixing the audit findings."""
from datetime import date, timedelta


from app.db import models as m
from app.db.session import make_session_factory
from app.ml.baseline import forecast_day
from app.services.forecasting import HISTORY_DAYS, load_hourly_series
from tests.api.helpers import lab_payload


def reading(client, lab_id, timestamp, value="1.0"):
    return client.post("/api/readings", json={"lab_id": lab_id, "timestamp": timestamp, "value": value,
                                              "reading_type": "measured", "source": "t"})


def test_archived_laboratory_is_hidden_refuses_readings_and_can_be_restored(client):
    lab_id = client.post("/api/labs", json=lab_payload(name="Old Lab")).json()["id"]
    assert client.post(f"/api/labs/{lab_id}/archive").status_code == 200
    names = [lab["name"] for lab in client.get("/api/labs").json()]
    assert "Old Lab" not in names
    assert "Old Lab" in [lab["name"] for lab in client.get("/api/labs?include_archived=true").json()]
    refused = reading(client, lab_id, "2026-10-01T00:00:00Z")
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "laboratory_archived"
    assert client.post(f"/api/labs/{lab_id}/restore").status_code == 200
    assert reading(client, lab_id, "2026-10-01T00:00:00Z").status_code == 201


def test_import_rejects_rows_for_archived_laboratories(client):
    lab_id = client.post("/api/labs", json=lab_payload(name="Closed Lab")).json()["id"]
    client.post(f"/api/labs/{lab_id}/archive")
    csv = b"lab_name,timestamp,value,reading_type\nClosed Lab,2026-10-01T00:00:00Z,1.0,measured\n"
    result = client.post("/api/imports/readings", files={"file": ("c.csv", csv, "text/csv")}).json()
    assert result["accepted"] == 0 and result["rejected"] == 1
    assert "archived" in result["problems"][0]["reason"]


def test_archiving_needs_the_labs_write_permission(role_client, make_lab):
    lab_id = make_lab("Protected Lab")
    assert role_client("staff").post(f"/api/labs/{lab_id}/archive").status_code == 403


def test_alert_count_matches_the_list_and_respects_filters(client):
    client.post("/api/alerts/detect", json={})
    total = client.get("/api/alerts/count").json()["total"]
    listed = client.get("/api/alerts?limit=500").json()
    assert total == len(listed)
    assert client.get("/api/alerts/count?status=resolved").json()["total"] == 0


def test_data_range_reports_first_and_last_local_day(client, make_lab):
    lab_id = make_lab("Range Lab", timezone="Asia/Kolkata")
    empty = client.get(f"/api/labs/{lab_id}/data-range").json()
    assert empty["first_day"] is None
    # 20:00 UTC on 1 Oct is 01:30 on 2 Oct in India
    reading(client, lab_id, "2026-10-01T20:00:00Z")
    reading(client, lab_id, "2026-10-03T10:00:00Z")
    body = client.get(f"/api/labs/{lab_id}/data-range").json()
    assert body["first_day"] == "2026-10-02" and body["last_day"] == "2026-10-03"


def test_schedules_with_minutes_are_refused_through_the_api(client, make_lab):
    lab_id = make_lab()
    response = client.post(f"/api/labs/{lab_id}/schedules", json={
        "weekday": 0, "open_time": "08:30:00", "close_time": "17:00:00", "valid_from": "2026-07-01"})
    assert response.status_code == 422
    assert "whole hour" in response.text


def test_bounded_history_gives_the_same_baseline_forecast_as_full_history(engine, client, make_lab):
    """Limiting the history read from the database must not change any forecast."""
    lab_id = make_lab("History Lab", timezone="UTC")
    start = date(2026, 1, 5)  # a Monday
    rows = []
    for d in range(150):
        day = start + timedelta(days=d)
        for h in range(24):
            value = 1.0 + (day.weekday() * 0.7) + (h * 0.05) + ((d * 13 + h * 7) % 11) * 0.01
            rows.append(f"{lab_id},{day.isoformat()}T{h:02d}:00:00Z,{value:.4f},measured")
    csv = "lab_id,timestamp,value,reading_type\n" + "\n".join(rows)
    response = client.post("/api/imports/readings", files={"file": ("h.csv", csv.encode(), "text/csv")})
    assert response.status_code == 200 and response.json()["accepted"] == 150 * 24

    target = start + timedelta(days=140)
    with make_session_factory(engine)() as session:
        lab = session.get(m.Laboratory, lab_id)
        full, _ = load_hourly_series(session, lab)
        bounded, _ = load_hourly_series(session, lab, start_day=target - timedelta(days=HISTORY_DAYS),
                                        end_day=target - timedelta(days=1))
        assert len(bounded) < len(full)  # the bounded read really does read less
        assert forecast_day(full, target, k=8)["hourly"] == forecast_day(bounded, target, k=8)["hourly"]
