from datetime import date

import pytest

import generate_synthetic_data as gen
from app.ml.registry import ModelRegistry
from app.ml.training import train_and_evaluate
from app.services.forecasting import load_training_inputs
from app.db.session import make_session_factory
from tests.api.helpers import load_synthetic_dataset


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("models-data")
    gen.generate_dataset(start=date(2026, 7, 6), days=56, seed=11, out_dir=out)
    return out


@pytest.fixture()
def trained(client, app, engine, dataset, tmp_path):
    """Load the synthetic data and train small models into a temporary directory."""
    ids = load_synthetic_dataset(client, dataset)
    with make_session_factory(engine)() as session:
        inputs = load_training_inputs(session)
    report = train_and_evaluate(inputs, tmp_path / "models", n_estimators=10)
    app.state.model_registry = ModelRegistry(tmp_path / "models")
    return {"ids": ids, "report": report}


def test_random_forest_forecast_is_saved_with_its_model_version(client, trained):
    response = client.post("/api/forecasts", json={
        "lab_id": trained["ids"]["Electronics Lab"], "target_date": "2026-08-24", "model": "random_forest"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["model_name"] == "random_forest" and body["model_version"] == "v1"
    assert body["details"]["model"]["name"] == "random_forest"
    assert len(body["details"]["hourly_kwh"]) == 24
    assert all(v >= 0 for v in body["details"]["hourly_kwh"])
    assert float(body["predicted_kwh"]) > 0


def test_linear_forecast_works_and_records_its_trained_window(client, trained):
    response = client.post("/api/forecasts", json={
        "lab_id": trained["ids"]["Programming Lab 1"], "target_date": "2026-08-24", "model": "linear_regression"})
    assert response.status_code == 201, response.text
    assert response.json()["details"]["model"]["trained_on"]["end"] < "2026-08-24"


def test_model_refuses_days_inside_its_training_period(client, trained):
    response = client.post("/api/forecasts", json={
        "lab_id": trained["ids"]["Electronics Lab"], "target_date": "2026-08-10", "model": "random_forest"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "outside_training_window"
    assert error["details"]["trained_through"] == "2026-08-21"


def test_the_last_training_day_itself_is_refused(client, trained):
    trained_through = trained["report"]["split"]["validation"]["end"]
    response = client.post("/api/forecasts", json={
        "lab_id": trained["ids"]["Electronics Lab"], "target_date": trained_through, "model": "random_forest"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "outside_training_window"


def test_ml_forecast_without_enough_history_is_refused(client, trained):
    lab_id = client.post("/api/labs", json={"name": "Sparse Lab", "building": "B", "lab_type": "T",
                                            "computer_count": 10, "timezone": "UTC"}).json()["id"]
    rows = ["lab_id,timestamp,value,reading_type"]
    rows += [f"{lab_id},2026-08-0{d}T{h:02d}:00:00Z,1.0,measured" for d in range(1, 4) for h in range(24)]
    client.post("/api/imports/readings", files={"file": ("sparse.csv", "\n".join(rows).encode(), "text/csv")})
    response = client.post("/api/forecasts", json={
        "lab_id": lab_id, "target_date": "2026-08-24", "model": "random_forest"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_history"
    assert response.json()["error"]["details"]["missing_hours"]


def test_ml_forecast_is_unavailable_until_models_are_trained(client, app, trained, tmp_path):
    app.state.model_registry = ModelRegistry(tmp_path / "empty")
    response = client.post("/api/forecasts", json={
        "lab_id": trained["ids"]["Electronics Lab"], "target_date": "2026-08-24", "model": "random_forest"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable"


def test_baseline_forecast_still_works_without_any_trained_model(client, app, trained, tmp_path):
    app.state.model_registry = ModelRegistry(tmp_path / "empty")
    response = client.post("/api/forecasts", json={
        "lab_id": trained["ids"]["Electronics Lab"], "target_date": "2026-08-10"})
    assert response.status_code == 201


def test_comparison_endpoint_returns_the_saved_report(client, trained):
    body = client.get("/api/models/comparison").json()
    assert body["test"]["baseline"]["mae"] >= 0
    assert set(body["test"]["random_forest"]["vs_baseline"]) == {"mae", "rmse"}
    assert "verdict" in body["test"]["random_forest"]["vs_baseline"]["mae"]


def test_status_lists_models_and_their_features(client, trained):
    status = client.get("/api/models/status").json()
    assert set(status["models"]) == {"linear_regression", "random_forest"}
    assert "is_weekend" not in status["models"]["random_forest"]["feature_names"]


def test_comparison_is_404_before_training(client, app, tmp_path):
    app.state.model_registry = ModelRegistry(tmp_path / "nothing")
    response = client.get("/api/models/comparison")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_trained"


def test_model_views_are_open_to_every_signed_in_role(role_client, trained):
    assert role_client("evaluator").get("/api/models/comparison").status_code == 200
    assert role_client("staff").get("/api/models/status").status_code == 200


def test_only_roles_that_can_forecast_may_request_one(role_client, trained):
    denied = role_client("evaluator").post("/api/forecasts", json={
        "lab_id": trained["ids"]["Electronics Lab"], "target_date": "2026-08-10", "model": "random_forest"})
    assert denied.status_code == 403
