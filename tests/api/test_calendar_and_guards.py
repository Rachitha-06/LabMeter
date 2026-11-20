
from tests.api.helpers import lab_payload


def test_calendar_days_can_be_loaded_and_read_back(client):
    response = client.put("/api/calendar", json={"days": [
        {"day": "2026-08-15", "is_holiday": True, "label": "Independence Day"},
        {"day": "2026-09-14", "is_exam_period": True}]})
    assert response.status_code == 200
    assert response.json() == {"created": 2, "updated": 0}
    again = client.put("/api/calendar", json={"days": [{"day": "2026-08-15", "is_holiday": False}]})
    assert again.json() == {"created": 0, "updated": 1}
    days = client.get("/api/calendar?start=2026-08-01&end=2026-09-30").json()
    assert [d["day"] for d in days] == ["2026-08-15", "2026-09-14"]
    assert days[0]["is_holiday"] is False


def test_calendar_batch_rejects_duplicate_days(client):
    response = client.put("/api/calendar", json={"days": [{"day": "2026-08-15"}, {"day": "2026-08-15"}]})
    assert response.status_code == 422


def test_calendar_write_is_limited_to_managers(role_client):
    body = {"days": [{"day": "2026-08-15", "is_holiday": True}]}
    assert role_client("staff").put("/api/calendar", json=body).status_code == 403
    assert role_client("lab_manager").put("/api/calendar", json=body).status_code == 200


def test_a_lab_without_operating_hours_is_not_screened(client):
    lab_id = client.post("/api/labs", json=lab_payload(name="No Hours Lab")).json()["id"]
    rows = ["lab_id,timestamp,value,reading_type"]
    rows += [f"{lab_id},2026-08-{d:02d}T{h:02d}:00:00Z,5.0,measured" for d in range(1, 22) for h in range(24)]
    client.post("/api/imports/readings", files={"file": ("n.csv", "\n".join(rows).encode(), "text/csv")})
    summary = client.post("/api/alerts/detect", json={"lab_id": lab_id}).json()
    assert summary["created"] == 0
    assert summary["labs_without_schedule"] == 1
    assert client.get("/api/alerts").json() == []
