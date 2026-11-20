"""Regression tests for the audit findings fixed in this round."""
from datetime import date, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.alerts import local_to_utc
from app.services.reports import safe_cell
from app.validation.schemas import ScheduleCreate
from pydantic import ValidationError


def test_csv_formula_cells_are_neutralised():
    assert safe_cell("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert safe_cell("+1+1") == "'+1+1"
    assert safe_cell("@SUM(A1)") == "'@SUM(A1)"
    assert safe_cell("Programming Lab 1") == "Programming Lab 1"
    assert safe_cell(3.5) == 3.5


def test_security_headers_are_sent_on_every_response():
    client = TestClient(create_app(frontend_dist=__import__("pathlib").Path("/nonexistent")))
    headers = client.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "strict-transport-security" not in headers  # only added when HSTS_ENABLED=1


def test_api_docs_are_off_by_default():
    client = TestClient(create_app(frontend_dist=__import__("pathlib").Path("/nonexistent")))
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_unexpected_errors_return_a_generic_message_with_a_request_id():
    app = create_app(frontend_dist=__import__("pathlib").Path("/nonexistent"))

    def boom():
        raise RuntimeError("secret internal detail")

    app.add_api_route("/api/_boom", boom, methods=["GET"])
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/_boom")
    assert response.status_code == 500
    body = response.json()["error"]
    assert body["code"] == "internal_error"
    assert "secret internal detail" not in response.text
    assert len(body["details"]["request_id"]) == 32


@pytest.mark.parametrize("value", ["08:30:00", "17:15:00"])
def test_schedules_must_use_whole_hours(value):
    with pytest.raises(ValidationError, match="whole hour"):
        ScheduleCreate(weekday=0, open_time=value, close_time="18:00:00", valid_from="2026-07-01")


def test_whole_hour_schedule_is_accepted():
    schedule = ScheduleCreate(weekday=0, open_time="08:00:00", close_time="18:00:00", valid_from="2026-07-01")
    assert schedule.open_time == time(8)


def test_daylight_saving_gap_hour_is_refused_and_repeated_hour_is_not_duplicated():
    ny = ZoneInfo("America/New_York")
    with pytest.raises(ValueError, match="does not exist"):
        local_to_utc(date(2026, 3, 8), 2, ny)          # 02:00 does not exist on spring-forward day
    assert local_to_utc(date(2026, 3, 8), 3, ny).isoformat() == "2026-03-08T07:00:00+00:00"
    assert local_to_utc(date(2026, 11, 1), 1, ny).isoformat() == "2026-11-01T05:00:00+00:00"  # first occurrence
    assert local_to_utc(date(2026, 3, 8), 1, ny).isoformat() == "2026-03-08T06:00:00+00:00"
