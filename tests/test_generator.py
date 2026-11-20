import csv
from datetime import date

import pytest

import generate_synthetic_data as gen


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("synthetic")
    gen.generate_dataset(start=date(2026, 7, 6), days=14, seed=7, out_dir=out)
    return out


def test_every_reading_is_labelled_simulated(dataset):
    rows = read_rows(dataset / "readings.csv")
    assert rows
    assert all(r["reading_type"] == "simulated" and r["source"] == gen.SOURCE for r in rows)


def test_no_negative_consumption(dataset):
    assert all(float(r["interval_kwh"]) >= 0 for r in read_rows(dataset / "readings.csv"))


def test_timestamps_are_utc(dataset):
    assert all(r["timestamp_utc"].endswith("Z") for r in read_rows(dataset / "readings.csv"))


def test_each_lab_has_hourly_rows_minus_the_deliberate_outage(dataset):
    rows = read_rows(dataset / "readings.csv")
    expected_full = 14 * 24
    for lab in gen.LABS:
        count = sum(1 for r in rows if r["lab_name"] == lab.name)
        # Each lab loses one outage window of up to 4 hours (fewer when it overlaps closing time).
        assert expected_full - 4 <= count < expected_full


def test_injected_anomalies_are_labelled_with_categories(dataset):
    anomalies = read_rows(dataset / "anomalies.csv")
    kinds = {a["anomaly_type"] for a in anomalies}
    assert {"after_hours_leftover", "stuck_high_load", "missing_data"} <= kinds
    categories = {a["suspected_category"] for a in anomalies}
    assert categories <= {"suspected_wastage", "legitimate", "data_quality"}


def test_provenance_states_the_data_is_synthetic(dataset):
    text = (dataset / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "synthetic" in text.lower()
    assert "do not represent any real" in text.lower()


def test_same_seed_produces_identical_readings(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    gen.generate_dataset(start=date(2026, 7, 6), days=14, seed=99, out_dir=first)
    gen.generate_dataset(start=date(2026, 7, 6), days=14, seed=99, out_dir=second)
    assert (first / "readings.csv").read_bytes() == (second / "readings.csv").read_bytes()


def test_different_seed_changes_the_readings(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    gen.generate_dataset(start=date(2026, 7, 6), days=14, seed=1, out_dir=first)
    gen.generate_dataset(start=date(2026, 7, 6), days=14, seed=2, out_dir=second)
    assert (first / "readings.csv").read_bytes() != (second / "readings.csv").read_bytes()
