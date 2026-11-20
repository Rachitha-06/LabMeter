import csv
from datetime import date

import pytest

import generate_synthetic_data as gen
from tests.api.helpers import lab_payload


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("forecast-data")
    gen.generate_dataset(start=date(2026, 7, 6), days=56, seed=11, out_dir=out)
    return out


@pytest.fixture()
def loaded(client, dataset):
    """Create the three synthetic laboratories and import their readings. Returns name -> id."""
    with (dataset / "labs.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            client.post("/api/labs", json=lab_payload(
                name=row["name"], building=row["building"], lab_type=row["lab_type"],
                computer_count=int(row["computer_count"]), timezone=row["timezone"]))
    response = client.post("/api/imports/readings",
                           files={"file": ("readings.csv", (dataset / "readings.csv").read_bytes(), "text/csv")})
    assert response.status_code == 200, response.text
    return {lab["name"]: lab["id"] for lab in client.get("/api/labs").json()}


def test_monday_forecast_is_built_only_from_earlier_mondays(client, loaded):
    response = client.post("/api/forecasts", json={
        "lab_id": loaded["Electronics Lab"], "target_date": "2026-08-10", "comparable_days": 4, "min_history": 2})
    assert response.status_code == 201, response.text
    body = response.json()
    details = body["details"]
    assert details["comparable_days"] == ["2026-07-13", "2026-07-20", "2026-07-27", "2026-08-03"]  # the 4 most recent Mondays
    assert all(date.fromisoformat(d).weekday() == 0 for d in details["comparable_days"])
    assert all(d < "2026-08-10" for d in details["comparable_days"])
    assert len(details["hourly_kwh"]) == 24
    assert float(body["predicted_kwh"]) == pytest.approx(details["total_kwh"], abs=1e-3)
    assert float(body["predicted_kwh"]) > 0
    assert "Not measured consumption" in details["note"]


def test_forecast_without_enough_history_is_refused_with_detail(client, loaded):
    response = client.post("/api/forecasts", json={
        "lab_id": loaded["Electronics Lab"], "target_date": "2026-07-07", "comparable_days": 4, "min_history": 2})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "insufficient_history"
    assert error["details"]["comparable_days_found"] == 0


def test_saved_forecasts_can_be_listed_and_opened(client, loaded):
    created = client.post("/api/forecasts", json={
        "lab_id": loaded["Electronics Lab"], "target_date": "2026-08-10"}).json()
    listed = client.get(f"/api/forecasts?lab_id={loaded['Electronics Lab']}").json()
    assert any(f["id"] == created["id"] for f in listed)
    fetched = client.get(f"/api/forecasts/{created['id']}").json()
    assert fetched["details"]["hourly_kwh"] == created["details"]["hourly_kwh"]
    assert fetched["horizon_start"] < fetched["horizon_end"]


def test_forecast_request_rules_are_enforced(client, loaded):
    lab_id = loaded["Electronics Lab"]
    assert client.post("/api/forecasts", json={"lab_id": lab_id, "target_date": "2026-08-10",
                                               "comparable_days": 2, "min_history": 3}).status_code == 422
    assert client.post("/api/forecasts", json={"lab_id": lab_id, "target_date": "2026-08-10",
                                               "comparable_days": 0}).status_code == 422
    assert client.post("/api/forecasts", json={"lab_id": 9999, "target_date": "2026-08-10"}).status_code == 404


def test_evaluation_reports_chronological_split_and_test_accuracy(client, loaded):
    report = client.get(f"/api/forecasts/evaluation?lab_id={loaded['Electronics Lab']}").json()
    split = report["split"]
    assert split["train"]["end"] < split["validation"]["start"] < split["validation"]["end"] < split["test"]["start"]
    assert report["chosen_k"] in (1, 2, 3, 4, 6, 8)
    assert report["test"]["days_evaluated"] > 0
    assert report["test"]["hours_evaluated"] > 0
    assert report["test"]["rmse"] >= report["test"]["mae"] >= 0
    assert report["notes"]
    assert all({"date", "actual_kwh", "predicted_kwh"} <= set(d) for d in report["daily"])


def test_evaluation_refuses_too_little_data(client, make_lab):
    lab_id = make_lab("Brand New Lab")
    rows = ["lab_id,timestamp,value,reading_type"]
    rows += [f"{lab_id},2026-10-0{d}T{h:02d}:00:00Z,1.0,measured" for d in range(1, 4) for h in range(24)]
    response = client.post("/api/imports/readings", files={"file": ("small.csv", "\n".join(rows).encode(), "text/csv")})
    assert response.status_code == 200
    refused = client.get(f"/api/forecasts/evaluation?lab_id={lab_id}")
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "insufficient_history"


def test_evaluator_can_read_forecasts_but_not_create_them(client, role_client, loaded):
    created = client.post("/api/forecasts", json={"lab_id": loaded["Electronics Lab"], "target_date": "2026-08-10"})
    assert created.status_code == 201
    evaluator = role_client("evaluator")
    assert evaluator.get("/api/forecasts/evaluation?lab_id=" + str(loaded["Electronics Lab"])).status_code == 200
    assert evaluator.get(f"/api/forecasts/{created.json()['id']}").status_code == 200
    denied = evaluator.post("/api/forecasts", json={"lab_id": loaded["Electronics Lab"], "target_date": "2026-08-10"})
    assert denied.status_code == 403
