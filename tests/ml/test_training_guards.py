import json

import numpy as np
import pytest

from app.ml.registry import ModelRegistry, ModelUnavailable
from app.ml.training import paired_bootstrap, predict_hours
from app.ml.features import FEATURE_NAMES


def test_bootstrap_detects_a_clearly_more_accurate_model():
    rng = np.random.default_rng(1)
    days = np.repeat(np.arange(20), 24)
    baseline_err = rng.normal(0, 1.0, days.size)
    model_err = baseline_err * 0.2  # the model's errors are much smaller
    result = paired_bootstrap(days, model_err, baseline_err, metric="mae", resamples=500)
    assert result["ci95"][1] < 0
    assert "more accurate" in result["verdict"]


def test_bootstrap_reports_no_difference_for_identical_errors():
    rng = np.random.default_rng(2)
    days = np.repeat(np.arange(15), 24)
    errors = rng.normal(0, 1.0, days.size)
    result = paired_bootstrap(days, errors, errors, metric="rmse", resamples=300)
    assert result["difference"] == 0
    assert "no clear difference" in result["verdict"]


def test_bootstrap_rejects_unknown_metric():
    with pytest.raises(ValueError):
        paired_bootstrap(np.arange(3), np.ones(3), np.ones(3), metric="mape")


def test_predictions_are_bounded_between_zero_and_the_ceiling():
    class Wild:
        def predict(self, frame):
            return np.array([-5.0, 3.0, 1e12])
    rows = [{name: 0.0 for name in FEATURE_NAMES} for _ in range(3)]
    assert predict_hours(Wild(), rows, ceiling_kwh=10.0) == [0.0, 3.0, 10.0]


def test_registry_refuses_models_trained_on_a_different_feature_set(tmp_path):
    (tmp_path / "metadata.json").write_text(json.dumps({"models": {
        "random_forest": {"file": "rf.joblib", "feature_names": ["hour"], "model_version": "v1",
                          "trained_on": {}, "prediction_ceiling_kwh": 1.0}}}))
    with pytest.raises(ModelUnavailable, match="feature definition changed"):
        ModelRegistry(tmp_path).get("random_forest")


def test_registry_reports_missing_artifacts_clearly(tmp_path):
    with pytest.raises(ModelUnavailable, match="train_models"):
        ModelRegistry(tmp_path).metadata()
    with pytest.raises(ModelUnavailable, match="train_models"):
        ModelRegistry(tmp_path).report()


def test_registry_refuses_models_from_another_scikit_learn_version(tmp_path):
    import sklearn
    (tmp_path / "metadata.json").write_text(json.dumps({"models": {
        "random_forest": {"file": "rf.joblib", "feature_names": FEATURE_NAMES, "model_version": "v1",
                          "trained_on": {}, "prediction_ceiling_kwh": 1.0,
                          "sklearn_version": "0.0.1"}}}))
    with pytest.raises(ModelUnavailable, match="trained with scikit-learn"):
        ModelRegistry(tmp_path).get("random_forest")
    assert sklearn.__version__  # the installed version is what the message compares against


def test_registry_refuses_models_without_a_recorded_version(tmp_path):
    (tmp_path / "metadata.json").write_text(json.dumps({"models": {
        "random_forest": {"file": "rf.joblib", "feature_names": FEATURE_NAMES, "model_version": "v1",
                          "trained_on": {}, "prediction_ceiling_kwh": 1.0}}}))
    with pytest.raises(ModelUnavailable, match="unrecorded version"):
        ModelRegistry(tmp_path).get("random_forest")
