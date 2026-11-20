from datetime import date

import pytest

import generate_synthetic_data as gen
from app.db.session import make_session_factory
from app.services.alert_evaluation import evaluate_against_labels
from tests.api.helpers import load_synthetic_dataset


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("alerts-data")
    gen.generate_dataset(start=date(2026, 7, 6), days=56, seed=11, out_dir=out)
    return out


@pytest.fixture()
def loaded(client, dataset):
    return load_synthetic_dataset(client, dataset)


def test_detection_creates_alerts_with_explanations(client, loaded):
    summary = client.post("/api/alerts/detect", json={}).json()
    assert summary["created"] >= 1
    alerts = client.get("/api/alerts").json()
    assert len(alerts) == summary["created"]
    first = alerts[0]
    assert first["rule_id"] == "unoccupied_excess_v1"
    assert first["status"] == "open"
    assert float(first["actual_kwh"]) > float(first["expected_kwh"])
    assert "suspected excess for review" in first["explanation"]
    assert "not a confirmed waste" in first["explanation"]


def test_rerunning_detection_never_duplicates_alerts(client, loaded):
    first = client.post("/api/alerts/detect", json={}).json()
    second = client.post("/api/alerts/detect", json={}).json()
    assert second["created"] == 0
    assert second["already_recorded"] == first["created"]
    assert len(client.get("/api/alerts").json()) == first["created"]


def test_detection_can_be_limited_to_a_lab_and_date_window(client, loaded):
    summary = client.post("/api/alerts/detect", json={
        "lab_id": loaded["Electronics Lab"], "start": "2026-07-06", "end": "2026-07-19"}).json()
    assert summary["labs"] == 1
    assert all(a["lab_name"] == "Electronics Lab" for a in client.get("/api/alerts").json())


def test_detection_refuses_unknown_lab_and_bad_window(client, loaded):
    assert client.post("/api/alerts/detect", json={"lab_id": 9999}).status_code == 404
    assert client.post("/api/alerts/detect", json={"start": "2026-07-10", "end": "2026-07-01"}).status_code == 422


def test_alerts_can_be_filtered_by_status_and_lab(client, loaded):
    client.post("/api/alerts/detect", json={})
    alerts = client.get("/api/alerts").json()
    client.patch(f"/api/alerts/{alerts[0]['id']}", json={"status": "under_review"})
    under = client.get("/api/alerts?status=under_review").json()
    assert [a["id"] for a in under] == [alerts[0]["id"]]
    lab_name = alerts[0]["lab_name"]
    assert all(a["lab_name"] == lab_name for a in client.get(f"/api/alerts?lab_id={alerts[0]['lab_id']}").json())


def test_review_workflow_follows_allowed_transitions(client, loaded):
    client.post("/api/alerts/detect", json={})
    alert = client.get("/api/alerts").json()[0]
    under = client.patch(f"/api/alerts/{alert['id']}", json={"status": "under_review", "comment": "checking the meter"})
    assert under.status_code == 200 and under.json()["status"] == "under_review"
    resolved = client.patch(f"/api/alerts/{alert['id']}", json={
        "status": "resolved", "comment": "equipment had been left on; switched off"})
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    detail = client.get(f"/api/alerts/{alert['id']}").json()
    assert [r["to_status"] for r in detail["reviews"]] == ["under_review", "resolved"]
    assert detail["reviews"][-1]["comment"].startswith("equipment had been left on")


def test_resolving_requires_an_explanation(client, loaded):
    client.post("/api/alerts/detect", json={})
    alert = client.get("/api/alerts").json()[0]
    response = client.patch(f"/api/alerts/{alert['id']}", json={"status": "resolved"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


def test_impossible_transitions_are_refused(client, loaded):
    client.post("/api/alerts/detect", json={})
    alert = client.get("/api/alerts").json()[0]
    client.patch(f"/api/alerts/{alert['id']}", json={"status": "resolved", "comment": "reviewed and closed"})
    back = client.patch(f"/api/alerts/{alert['id']}", json={"status": "under_review"})
    assert back.status_code == 409
    same = client.patch(f"/api/alerts/{alert['id']}", json={"status": "resolved", "comment": "again"})
    assert same.status_code == 409


def test_reopening_a_resolved_alert_is_allowed(client, loaded):
    client.post("/api/alerts/detect", json={})
    alert = client.get("/api/alerts").json()[0]
    client.patch(f"/api/alerts/{alert['id']}", json={"status": "resolved", "comment": "closed in error"})
    reopened = client.patch(f"/api/alerts/{alert['id']}", json={"status": "open", "comment": "new evidence"})
    assert reopened.status_code == 200 and reopened.json()["status"] == "open"


def test_comments_are_kept_without_changing_status(client, loaded):
    client.post("/api/alerts/detect", json={})
    alert = client.get("/api/alerts").json()[0]
    response = client.post(f"/api/alerts/{alert['id']}/comments", json={"comment": "asked the lab manager"})
    assert response.status_code == 201
    detail = client.get(f"/api/alerts/{alert['id']}").json()
    assert detail["status"] == "open"
    assert detail["reviews"][-1]["from_status"] == detail["reviews"][-1]["to_status"] == "open"


def test_reviews_record_who_made_them(client, loaded):
    client.post("/api/alerts/detect", json={})
    alert = client.get("/api/alerts").json()[0]
    me = client.get("/api/auth/me").json()["user"]
    client.patch(f"/api/alerts/{alert['id']}", json={"status": "under_review"})
    assert client.get(f"/api/alerts/{alert['id']}").json()["reviews"][-1]["user_id"] == me["id"]


def test_unknown_alert_is_404(client, loaded):
    assert client.get("/api/alerts/9999").status_code == 404
    assert client.patch("/api/alerts/9999", json={"status": "under_review"}).status_code == 404


def test_roles_can_only_do_what_they_should(client, role_client, loaded):
    client.post("/api/alerts/detect", json={})
    alert_id = client.get("/api/alerts").json()[0]["id"]
    evaluator = role_client("evaluator")
    staff = role_client("staff")
    manager = role_client("lab_manager")
    assert evaluator.get("/api/alerts").status_code == 200
    assert evaluator.patch(f"/api/alerts/{alert_id}", json={"status": "under_review"}).status_code == 403
    assert evaluator.post("/api/alerts/detect", json={}).status_code == 403
    assert staff.post("/api/alerts/detect", json={}).status_code == 403
    assert staff.patch(f"/api/alerts/{alert_id}", json={"status": "under_review"}).status_code == 200
    assert manager.post("/api/alerts/detect", json={}).status_code == 200


def test_rule_on_generated_data_flags_injected_excess_and_no_legitimate_periods(client, engine, loaded, dataset):
    client.post("/api/alerts/detect", json={})
    import csv
    labels = list(csv.DictReader((dataset / "anomalies.csv").open(encoding="utf-8")))
    with make_session_factory(engine)() as session:
        report = evaluate_against_labels(session, labels)
    assert report["precision"] == 1.0
    assert report["false_positive_hours_on_legitimate_periods"] == 0
    assert report["false_positive_hours_on_data_quality_periods"] == 0
    assert report["recall_on_assessable_hours"] == 1.0
