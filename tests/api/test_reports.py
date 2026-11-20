import csv
import io
from datetime import date

import pytest

import generate_synthetic_data as gen
from tests.api.helpers import load_synthetic_dataset


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("report-data")
    gen.generate_dataset(start=date(2026, 7, 6), days=28, seed=5, out_dir=out)
    return out


def test_report_lists_each_lab_day_with_kwh_split_by_type(client, dataset):
    ids = load_synthetic_dataset(client, dataset)
    body = client.get("/api/reports/energy", params={
        "start": "2026-07-06T00:00:00Z", "end": "2026-07-13T00:00:00Z", "lab_id": ids["Electronics Lab"]}).json()
    assert body["laboratories"] == ["Electronics Lab"]
    # The window starts at 00:00 UTC, which is 05:30 in India, so eight local days are touched.
    dates = [r["date"] for r in body["rows"]]
    assert dates == [f"2026-07-{d:02d}" for d in range(6, 14)]
    row = body["rows"][0]
    assert float(row["simulated_kwh"]) > 0 and float(row["measured_kwh"]) == 0
    assert row["estimated_cost"] is None and row["estimated_emissions"] is None
    assert any("simulated" in note for note in body["notes"])
    assert any("No tariff" in note for note in body["notes"])


def test_csv_report_has_metadata_header_and_the_same_rows_as_json(client, dataset):
    ids = load_synthetic_dataset(client, dataset)
    params = {"start": "2026-07-06T00:00:00Z", "end": "2026-07-13T00:00:00Z", "lab_id": ids["Programming Lab 1"]}
    json_rows = client.get("/api/reports/energy", params=params).json()["rows"]
    response = client.get("/api/reports/energy", params={**params, "format": "csv"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    text = response.text
    assert text.startswith("# LabMeter Suite energy report")
    data_lines = [line for line in text.splitlines() if not line.startswith("#")]
    rows = list(csv.DictReader(io.StringIO("\n".join(data_lines))))
    assert [r["date"] for r in rows] == [r["date"] for r in json_rows]
    assert [r["total_kwh"] for r in rows] == [r["total_kwh"] for r in json_rows]


def test_report_includes_costs_once_configured(client, dataset):
    ids = load_synthetic_dataset(client, dataset)
    client.post("/api/tariffs", json={"rate_per_kwh": "10.0000", "currency": "INR", "effective_from": "2026-01-01",
                                      "source": "TEST VALUE for report test"})
    client.post("/api/emission-factors", json={"value": "0.5", "unit": "kgCO2e/kWh", "effective_from": "2026-01-01",
                                               "version_or_year": "TEST", "source": "TEST VALUE for report test"})
    body = client.get("/api/reports/energy", params={
        "start": "2026-07-06T00:00:00Z", "end": "2026-07-13T00:00:00Z", "lab_id": ids["Electronics Lab"]}).json()
    row = body["rows"][0]
    assert row["cost_currency"] == "INR" and row["emission_unit"] == "kgCO2e/kWh"
    assert float(row["estimated_cost"]) == pytest.approx(float(row["total_kwh"]) * 10, abs=0.01)


def test_report_refuses_bad_windows_and_unknown_labs(client):
    assert client.get("/api/reports/energy", params={
        "start": "2026-07-10T00:00:00Z", "end": "2026-07-01T00:00:00Z"}).status_code == 422
    assert client.get("/api/reports/energy", params={
        "start": "2024-01-01T00:00:00Z", "end": "2026-07-01T00:00:00Z"}).status_code == 422
    assert client.get("/api/reports/energy", params={
        "start": "2026-07-01T00:00:00Z", "end": "2026-07-02T00:00:00Z", "lab_id": 999}).status_code == 404


def test_every_signed_in_role_can_read_reports(role_client, client, dataset):
    load_synthetic_dataset(client, dataset)
    params = {"start": "2026-07-06T00:00:00Z", "end": "2026-07-08T00:00:00Z"}
    assert role_client("evaluator").get("/api/reports/energy", params=params).status_code == 200
    assert role_client("staff").get("/api/reports/energy", params={**params, "format": "csv"}).status_code == 200
