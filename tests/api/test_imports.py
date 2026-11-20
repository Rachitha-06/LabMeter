import csv
from datetime import date

from fastapi.testclient import TestClient

import generate_synthetic_data as gen
from app.db.session import make_session_factory
from app.main import create_app
from tests.api.helpers import lab_payload


def upload(client, content: bytes, name="readings.csv", **params):
    return client.post("/api/imports/readings", params=params,
                       files={"file": (name, content, "text/csv")})


def csv_bytes(header, rows):
    lines = [",".join(header)] + [",".join(str(v) for v in row) for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def stored_readings(client):
    return client.get("/api/readings?limit=1000").json()


def test_full_synthetic_dataset_imports_and_reimport_is_all_duplicates(client, tmp_path):
    gen.generate_dataset(start=date(2026, 7, 6), days=14, seed=7, out_dir=tmp_path)
    with (tmp_path / "labs.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            client.post("/api/labs", json=lab_payload(
                name=row["name"], building=row["building"], lab_type=row["lab_type"],
                computer_count=int(row["computer_count"]), timezone=row["timezone"]))
    content = (tmp_path / "readings.csv").read_bytes()

    first = upload(client, content).json()
    total = first["rows_total"]
    assert first["accepted"] == total and first["rejected"] == 0 and first["conflicts"] == 0
    assert first["batch_id"] is not None

    second = upload(client, content).json()
    assert second["accepted"] == 0
    assert second["duplicates"] == total
    assert len(stored_readings(client)) == total


def test_import_reports_bad_rows_with_row_numbers_and_keeps_good_ones(client, make_lab):
    make_lab("Lab A")
    content = csv_bytes(
        ["lab_name", "timestamp", "value", "reading_type"],
        [
            ["Lab A", "2026-10-01T00:00:00Z", "1.0", "measured"],
            ["Lab A", "2026-10-01T01:00:00Z", "-1.0", "measured"],
            ["Nope", "2026-10-01T02:00:00Z", "1.0", "measured"],
            ["Lab A", "2026-10-01T03:00:00", "1.0", "measured"],
        ],
    )
    result = upload(client, content).json()
    assert result["accepted"] == 1
    assert result["rejected"] == 3
    assert sorted(p["row"] for p in result["problems"]) == [2, 3, 4]


def test_conflicting_value_against_stored_reading_is_reported_not_overwritten(client, make_lab):
    lab_id = make_lab()
    client.post("/api/readings", json={"lab_id": lab_id, "timestamp": "2026-10-01T00:00:00Z",
                                       "value": "1.0", "reading_type": "measured", "source": "manual"})
    content = csv_bytes(["lab_id", "timestamp", "value", "reading_type"],
                        [[lab_id, "2026-10-01T00:00:00Z", "2.0", "measured"]])
    result = upload(client, content).json()
    assert result["conflicts"] == 1 and result["accepted"] == 0
    assert result["problems"][0]["existing_kwh"] == "1.0000"
    assert stored_readings(client)[0]["interval_kwh"] == "1.0000"


def test_identical_rows_inside_one_file_count_once(client, make_lab):
    make_lab("Lab A")
    row = ["Lab A", "2026-10-01T00:00:00Z", "1.0", "measured"]
    result = upload(client, csv_bytes(["lab_name", "timestamp", "value", "reading_type"], [row, row])).json()
    assert result["accepted"] == 1 and result["duplicates"] == 1


def test_different_values_for_one_reading_inside_one_file_are_conflicts(client, make_lab):
    make_lab("Lab A")
    result = upload(client, csv_bytes(
        ["lab_name", "timestamp", "value", "reading_type"],
        [["Lab A", "2026-10-01T00:00:00Z", "1.0", "measured"],
         ["Lab A", "2026-10-01T00:00:00Z", "2.0", "measured"]],
    )).json()
    assert result["accepted"] == 1 and result["conflicts"] == 1


def test_dry_run_reports_without_writing(client, make_lab):
    make_lab("Lab A")
    content = csv_bytes(["lab_name", "timestamp", "value", "reading_type"],
                        [["Lab A", f"2026-10-01T0{h}:00:00Z", "1.0", "measured"] for h in range(3)])
    result = upload(client, content, dry_run=True).json()
    assert result["dry_run"] is True and result["accepted"] == 3 and result["batch_id"] is None
    assert stored_readings(client) == []
    assert client.get("/api/imports/1").status_code == 404


def test_missing_required_column_is_a_file_error(client):
    response = upload(client, csv_bytes(["lab_name", "value"], [["Lab A", "1"]]))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_file"
    assert "CSV must contain" in response.json()["error"]["message"]


def test_non_utf8_file_is_rejected(client):
    response = upload(client, b"\xff\xfe\x00bad")
    assert response.status_code == 422
    assert "UTF-8" in response.json()["error"]["message"]


def test_oversized_file_is_refused(engine):
    from tests.api.conftest import ADMIN_EMAIL, ADMIN_PASSWORD
    from tests.api.helpers import add_user, sign_in
    add_user(engine, ADMIN_EMAIL, ADMIN_PASSWORD, "admin")
    app = create_app(session_factory=make_session_factory(engine), max_import_bytes=50)
    with TestClient(app) as small:
        small.headers["Authorization"] = f"Bearer {sign_in(small, ADMIN_EMAIL, ADMIN_PASSWORD)}"
        response = upload(small, b"x" * 200)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_cumulative_meter_series_is_converted_with_reset_and_gap_handling(client, make_lab):
    make_lab("Lab A")
    rows = [
        ["Lab A", "2026-10-01T00:00:00Z", "100", "measured"],
        ["Lab A", "2026-10-01T01:00:00Z", "101.5", "measured"],
        ["Lab A", "2026-10-01T02:00:00Z", "103", "measured"],
        ["Lab A", "2026-10-01T03:00:00Z", "3", "measured"],   # meter reset
        ["Lab A", "2026-10-01T06:00:00Z", "5", "measured"],   # three hours missing before this
        ["Lab A", "2026-10-01T07:00:00Z", "6.5", "measured"],
    ]
    result = upload(client, csv_bytes(["lab_name", "timestamp", "cumulative_kwh", "reading_type"], rows)).json()
    assert result["accepted"] == 4
    assert result["skipped_baseline"] == 1
    assert result["skipped_gap"] == 1
    assert result["resets_flagged"] == 1

    readings = {r["timestamp_utc"][11:16]: r for r in stored_readings(client)}
    assert readings["03:00"]["quality_flag"] == "reset_assumed"
    assert float(readings["03:00"]["interval_kwh"]) == 3.0
    assert float(readings["07:00"]["interval_kwh"]) == 1.5
    assert "06:00" not in readings


def test_cumulative_import_uses_stored_value_from_an_earlier_file_as_baseline(client, make_lab):
    make_lab("Lab A")
    header = ["lab_name", "timestamp", "cumulative_kwh", "reading_type"]
    upload(client, csv_bytes(header, [["Lab A", "2026-10-01T00:00:00Z", "100", "measured"],
                                      ["Lab A", "2026-10-01T01:00:00Z", "101.5", "measured"]]))
    second = upload(client, csv_bytes(header, [["Lab A", "2026-10-01T02:00:00Z", "103", "measured"]])).json()
    assert second["accepted"] == 1
    assert second["skipped_baseline"] == 0
    assert float(stored_readings(client)[-1]["interval_kwh"]) == 1.5


def test_gap_detection_follows_the_declared_interval(client, make_lab):
    make_lab("Lab A")
    header = ["lab_name", "timestamp", "cumulative_kwh", "reading_type"]
    rows = [["Lab A", "2026-10-01T00:00:00Z", "100", "measured"],
            ["Lab A", "2026-10-01T01:00:00Z", "101", "measured"]]
    result = upload(client, csv_bytes(header, rows), interval_minutes=15).json()
    assert result["skipped_gap"] == 1 and result["accepted"] == 0


def test_lab_can_be_referenced_by_id_column(client, make_lab):
    lab_id = make_lab("Lab A")
    result = upload(client, csv_bytes(["lab_id", "timestamp", "value", "reading_type"],
                                      [[lab_id, "2026-10-01T00:00:00Z", "1.0", "measured"]])).json()
    assert result["accepted"] == 1


def test_batch_record_is_retrievable(client, make_lab):
    make_lab("Lab A")
    result = upload(client, csv_bytes(["lab_name", "timestamp", "value", "reading_type"],
                                      [["Lab A", "2026-10-01T00:00:00Z", "1.0", "measured"]])).json()
    batch = client.get(f"/api/imports/{result['batch_id']}").json()
    assert batch["rows_total"] == 1 and batch["rows_accepted"] == 1 and batch["status"] == "complete"
