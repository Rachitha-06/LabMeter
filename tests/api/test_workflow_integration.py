"""One pass through the whole system, using only the public API, the way an operator would use it.

Checks that the pieces agree with each other: the report, the estimates, and the alerts are computed
from the same readings, and the audit fields record who did what.
"""
import csv
import io
from datetime import date
from decimal import Decimal

import pytest

import generate_synthetic_data as gen
from fastapi.testclient import TestClient

from tests.api.conftest import ROLE_PASSWORD
from tests.api.helpers import add_user, load_synthetic_dataset, sign_in


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("integration")
    gen.generate_dataset(start=date(2026, 7, 6), days=56, seed=11, out_dir=out)
    return out


def test_full_workflow_from_setup_to_report(client, engine, role_client, dataset):
    # 1. Set up: laboratories, hours, calendar, readings (the same path an operator uses).
    ids = load_synthetic_dataset(client, dataset)
    assert len(ids) == 3

    # 2. Configure values the operator supplies. These are TEST values, not official ones.
    tariff = client.post("/api/tariffs", json={
        "rate_per_kwh": "10.0000", "currency": "INR", "effective_from": "2026-01-01",
        "source": "TEST VALUE for the integration test"})
    factor = client.post("/api/emission-factors", json={
        "value": "0.5000", "unit": "kgCO2e/kWh", "effective_from": "2026-01-01",
        "version_or_year": "TEST", "source": "TEST VALUE for the integration test"})
    assert tariff.status_code == 201 and factor.status_code == 201

    lab = ids["Electronics Lab"]
    window = {"start": "2026-07-06T00:00:00Z", "end": "2026-08-10T00:00:00Z"}

    # 3. The estimate, the report, and the readings must agree on energy.
    estimate = client.get("/api/estimates/cost-emissions", params={**window, "lab_id": lab}).json()
    report = client.get("/api/reports/energy", params={**window, "lab_id": lab}).json()
    report_kwh = sum(Decimal(r["total_kwh"]) for r in report["rows"])
    assert report_kwh == Decimal(estimate["total"]["kwh"])
    assert sum(Decimal(r["estimated_cost"]) for r in report["rows"]) == Decimal(estimate["total"]["estimated_cost"])
    assert Decimal(estimate["total"]["estimated_cost"]) == (report_kwh * Decimal("10")).quantize(Decimal("0.01"))

    # 4. Screen for wastage and review one alert, with a named reviewer.
    summary = client.post("/api/alerts/detect", json={"lab_id": lab}).json()
    assert summary["created"] >= 1
    alert = client.get("/api/alerts", params={"lab_id": lab}).json()[0]
    reviewer = role_client("lab_manager")
    reviewer_id = reviewer.get("/api/auth/me").json()["user"]["id"]
    assert reviewer.patch(f"/api/alerts/{alert['id']}", json={"status": "under_review"}).status_code == 200
    assert reviewer.patch(f"/api/alerts/{alert['id']}", json={
        "status": "resolved", "comment": "equipment left on after close; reminder added to closing checklist"}).status_code == 200
    history = client.get(f"/api/alerts/{alert['id']}").json()
    assert history["status"] == "resolved"
    assert all(r["user_id"] == reviewer_id for r in history["reviews"])
    assert "not a confirmed waste" in history["explanation"]

    # 5. Re-running screening does not duplicate, and the resolved alert keeps its status.
    again = client.post("/api/alerts/detect", json={"lab_id": lab}).json()
    assert again["created"] == 0
    assert client.get(f"/api/alerts/{alert['id']}").json()["status"] == "resolved"

    # 6. The CSV export carries the same daily numbers as the JSON report.
    export = client.get("/api/reports/energy", params={**window, "lab_id": lab, "format": "csv"})
    data_lines = [line for line in export.text.splitlines() if not line.startswith("#")]
    csv_rows = list(csv.DictReader(io.StringIO("\n".join(data_lines))))
    assert [r["total_kwh"] for r in csv_rows] == [r["total_kwh"] for r in report["rows"]]
    assert sum(int(r["alerts_created"]) for r in csv_rows) == len(client.get("/api/alerts", params={"lab_id": lab}).json())

    # 7. Forecasts: the baseline works, the evaluation is chronological, and the saved record is retrievable.
    forecast = client.post("/api/forecasts", json={"lab_id": lab, "target_date": "2026-08-10"})
    assert forecast.status_code == 201
    evaluation = client.get("/api/forecasts/evaluation", params={"lab_id": lab}).json()
    assert evaluation["split"]["train"]["end"] < evaluation["split"]["test"]["start"]

    # 8. Permissions hold across the whole flow: an evaluator reads everything and changes nothing.
    evaluator = role_client("evaluator")
    assert evaluator.get("/api/reports/energy", params=window).status_code == 200
    assert evaluator.post("/api/tariffs", json={"rate_per_kwh": "1", "currency": "INR", "effective_from": "2026-01-01",
                                                "source": "should be refused"}).status_code == 403
    assert evaluator.patch(f"/api/alerts/{alert['id']}", json={"status": "open"}).status_code == 403


def test_the_session_of_a_removed_user_stops_working_mid_workflow(client, engine, dataset):
    load_synthetic_dataset(client, dataset)
    add_user(engine, "temp.staff@example.test", ROLE_PASSWORD, "staff")
    with TestClient(client.app) as staff_client:
        token = sign_in(staff_client, "temp.staff@example.test", ROLE_PASSWORD)
        staff_client.headers["Authorization"] = f"Bearer {token}"
        assert staff_client.get("/api/labs").status_code == 200
        target = next(u for u in client.get("/api/auth/users").json() if u["email"] == "temp.staff@example.test")
        assert client.patch(f"/api/auth/users/{target['id']}", json={"is_active": False}).status_code == 200
        assert staff_client.get("/api/labs").status_code == 401
