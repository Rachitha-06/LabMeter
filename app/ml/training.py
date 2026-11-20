"""Training, model selection, evaluation, and artifact saving.

Protocol (chronological throughout):
1. Split all days into train, validation, and test periods (70/15/15).
2. Choose the baseline window k and the forest depth on the validation period only.
3. Score every model on the test period, using only data that precedes each test day.
4. Refit the chosen configurations on train plus validation for serving.

The reported test metrics come from the models fitted on the training period only, so they describe
a model that never saw the test period. The served models are refit on more data, which is standard
practice but means their test scores are not directly reported.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.ml.baseline import InsufficientHistory, forecast_day
from app.ml.features import CATEGORICAL, FEATURE_NAMES, build_rows
from app.ml.metrics import mae, rmse
from app.ml.registry import METADATA_FILE, REPORT_FILE
from app.ml.split import split_dates

MODEL_VERSION = "v1"
LINEAR = "linear_regression"
FOREST = "random_forest"
BASELINE_K_CANDIDATES = (1, 2, 3, 4, 6, 8)
FOREST_DEPTHS = (6, 12, None)
BOOTSTRAP_RESAMPLES = 2000
NUMERIC = [name for name in FEATURE_NAMES if name not in CATEGORICAL]


@dataclass
class TrainingInputs:
    series_by_lab: dict            # lab_id -> {date: [24 floats or None]}
    contexts: dict                 # lab_id -> LabContext
    calendar: dict                 # date -> CalendarDay
    lab_names: dict                # lab_id -> name
    timezones: dict                # lab_id -> IANA name


def build_frame(inputs: TrainingInputs) -> pd.DataFrame:
    rows: list[dict] = []
    for lab_id, series in inputs.series_by_lab.items():
        rows += build_rows(series, inputs.contexts[lab_id], inputs.calendar, sorted(series))
    if not rows:
        raise ValueError("no training rows: readings must cover at least 8 days")
    return pd.DataFrame(rows)


def all_days(inputs: TrainingInputs) -> list[date]:
    days: set[date] = set()
    for series in inputs.series_by_lab.values():
        days.update(series.keys())
    return sorted(days)


def make_linear() -> Pipeline:
    preprocess = ColumnTransformer([
        # drop="first" avoids collinearity with the intercept; an unseen category maps to the dropped level.
        ("categorical", OneHotEncoder(drop="first", handle_unknown="ignore"), CATEGORICAL),
        ("numeric", StandardScaler(), NUMERIC),
    ])
    return Pipeline([("preprocess", preprocess), ("model", LinearRegression())])


def make_forest(max_depth: Optional[int], n_estimators: int) -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=n_estimators, max_depth=max_depth, min_samples_leaf=5,
        random_state=42, n_jobs=1,
    )


def _mae_on(model, frame: pd.DataFrame) -> float:
    predicted = model.predict(frame[FEATURE_NAMES])
    return float(np.mean(np.abs(predicted - frame["target"].to_numpy())))


def _baseline_predictions(inputs: TrainingInputs, rows: pd.DataFrame, k: int, min_history: int = 2) -> dict:
    """(lab_id, day, hour) -> baseline prediction, for hours the baseline can forecast."""
    out: dict = {}
    for (lab_id, day), group in rows.groupby(["lab_id", "day"]):
        try:
            result = forecast_day(inputs.series_by_lab[int(lab_id)], day, k=k, min_history=min_history)
        except InsufficientHistory:
            continue
        for hour in group["hour"]:
            value = result["hourly"][int(hour)]
            if value is not None:
                out[(int(lab_id), day, int(hour))] = value
    return out


def _baseline_scores(inputs, frame, days_mask, k):
    subset = frame[days_mask]
    preds = _baseline_predictions(inputs, subset, k)
    pairs = [(preds[(int(r.lab_id), r.day, int(r.hour))], r.target)
             for r in subset.itertuples() if (int(r.lab_id), r.day, int(r.hour)) in preds]
    return pairs


def paired_bootstrap(days: np.ndarray, model_errors: np.ndarray, baseline_errors: np.ndarray,
                     metric: str = "mae", resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 0) -> dict:
    """Block bootstrap over test days, for MAE or RMSE. The statistic is model minus baseline.

    A negative value means the model is more accurate. Whole days are resampled, because hours within a
    day are not independent. The verdict is only "more accurate" or "less accurate" when the 95% interval
    excludes zero.
    """
    if metric not in ("mae", "rmse"):
        raise ValueError("metric must be 'mae' or 'rmse'")
    unique_days, inverse = np.unique(days, return_inverse=True)
    counts = np.bincount(inverse).astype(float)

    def per_day(errors):
        values = np.abs(errors) if metric == "mae" else errors ** 2
        return np.bincount(inverse, weights=values)

    model_sums, base_sums = per_day(model_errors), per_day(baseline_errors)

    def statistic(sel_counts, sel_model, sel_base):
        total = sel_counts.sum()
        if metric == "mae":
            return sel_model.sum() / total - sel_base.sum() / total
        return np.sqrt(sel_model.sum() / total) - np.sqrt(sel_base.sum() / total)

    point = statistic(counts, model_sums, base_sums)
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    for i in range(resamples):
        chosen = rng.integers(0, len(unique_days), len(unique_days))
        means[i] = statistic(counts[chosen], model_sums[chosen], base_sums[chosen])
    low, high = np.percentile(means, [2.5, 97.5])
    if high < 0:
        verdict = f"more accurate than the baseline on {metric.upper()} (95% interval excludes zero)"
    elif low > 0:
        verdict = f"less accurate than the baseline on {metric.upper()} (95% interval excludes zero)"
    else:
        verdict = f"no clear difference from the baseline on {metric.upper()} (95% interval includes zero)"
    return {"metric": metric.upper(), "difference": round(float(point), 4),
            "ci95": [round(float(low), 4), round(float(high), 4)], "resamples": resamples, "verdict": verdict}


def train_and_evaluate(inputs: TrainingInputs, out_dir: Path, n_estimators: int = 200) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = build_frame(inputs)
    days = all_days(inputs)
    train_days, val_days, test_days = split_dates(days)
    train_set, val_set, test_set = set(train_days), set(val_days), set(test_days)
    train = frame[frame["day"].isin(train_set)]
    val = frame[frame["day"].isin(val_set)]
    test = frame[frame["day"].isin(test_set)]
    if train.empty or val.empty or test.empty:
        raise ValueError("not enough complete rows in one of the periods; add more history")

    # 1. Baseline window k, chosen on validation.
    k_scores = {}
    for k in BASELINE_K_CANDIDATES:
        if k < 2:  # the baseline needs at least two comparable days, as in Phase 5
            continue
        pairs = _baseline_scores(inputs, frame, frame["day"].isin(val_set), k)
        if pairs:
            k_scores[k] = mae(pairs)
    chosen_k = min(k_scores, key=lambda k: (k_scores[k], k))

    # 2. Forest depth and model comparison, chosen on validation.
    linear_train = make_linear().fit(train[FEATURE_NAMES], train["target"])
    depth_scores = {}
    for depth in FOREST_DEPTHS:
        forest = make_forest(depth, n_estimators).fit(train[FEATURE_NAMES], train["target"])
        depth_scores[str(depth)] = _mae_on(forest, val)
    chosen_depth = min(FOREST_DEPTHS, key=lambda d: (depth_scores[str(d)], d is None, d or 0))

    # 3. Test period: models fitted on training data only.
    forest_train = make_forest(chosen_depth, n_estimators).fit(train[FEATURE_NAMES], train["target"])
    base_map = _baseline_predictions(inputs, test, chosen_k)
    keep = [i for i, r in test.iterrows() if (int(r["lab_id"]), r["day"], int(r["hour"])) in base_map]
    scored = test.loc[keep]
    keys = [(int(r["lab_id"]), r["day"], int(r["hour"])) for _, r in scored.iterrows()]
    baseline_pred = np.array([base_map[k] for k in keys])
    actual = scored["target"].to_numpy()
    linear_pred = linear_train.predict(scored[FEATURE_NAMES])
    forest_pred = forest_train.predict(scored[FEATURE_NAMES])
    score_days = scored["day"].to_numpy()

    def block(pred):
        pairs = list(zip(pred, actual))
        return {"mae": round(mae(pairs), 4), "rmse": round(rmse(pairs), 4)}

    base_err = baseline_pred - actual

    def compare(pred):
        errors = pred - actual
        return {"mae": paired_bootstrap(score_days, errors, base_err, metric="mae"),
                "rmse": paired_bootstrap(score_days, errors, base_err, metric="rmse")}

    test_block = {
        "baseline": block(baseline_pred),
        LINEAR: {**block(linear_pred), "vs_baseline": compare(linear_pred)},
        FOREST: {**block(forest_pred), "vs_baseline": compare(forest_pred)},
        "hours_compared": int(len(actual)),
        "days_compared": int(len(set(score_days))),
    }

    # 4. Serving models: refit on everything before the test period.
    fit_set = pd.concat([train, val])
    linear_serve = make_linear().fit(fit_set[FEATURE_NAMES], fit_set["target"])
    forest_serve = make_forest(chosen_depth, n_estimators).fit(fit_set[FEATURE_NAMES], fit_set["target"])
    trained_through = max(val_days).isoformat()
    ceiling = float(2.0 * fit_set["target"].max())  # sanity bound applied at serving time
    fingerprint = hashlib.sha256(
        fit_set[FEATURE_NAMES + ["lab_id", "target"]].to_csv(index=False).encode("utf-8")
    ).hexdigest()

    joblib.dump(linear_serve, out_dir / f"{LINEAR}.joblib")
    joblib.dump(forest_serve, out_dir / f"{FOREST}.joblib")
    common = {
        "model_version": MODEL_VERSION,
        "feature_names": FEATURE_NAMES,
        "trained_on": {"start": min(train_days).isoformat(), "end": trained_through},
        "training_rows": int(len(fit_set)),
        "training_fingerprint": fingerprint,
        "prediction_ceiling_kwh": round(ceiling, 4),
        "sklearn_version": sklearn.__version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata = {
        "models": {
            LINEAR: {**common, "file": f"{LINEAR}.joblib", "hyperparameters": {"preprocessing": "one-hot + scaled"}},
            FOREST: {**common, "file": f"{FOREST}.joblib",
                     "hyperparameters": {"n_estimators": n_estimators, "max_depth": chosen_depth,
                                         "min_samples_leaf": 5}},
        },
        "baseline": {"k": chosen_k, "min_history": 2},
    }
    (out_dir / METADATA_FILE).write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    report = {
        "split": {
            "train": {"start": min(train_days).isoformat(), "end": max(train_days).isoformat(), "days": len(train_days)},
            "validation": {"start": min(val_days).isoformat(), "end": max(val_days).isoformat(), "days": len(val_days)},
            "test": {"start": min(test_days).isoformat(), "end": max(test_days).isoformat(), "days": len(test_days)},
        },
        "selection": {
            "baseline_k_validation_mae": {str(k): round(v, 4) for k, v in k_scores.items()},
            "baseline_k_chosen": chosen_k,
            "forest_depth_validation_mae": {k: round(v, 4) for k, v in depth_scores.items()},
            "forest_depth_chosen": "none" if chosen_depth is None else chosen_depth,
            "validation_mae": {
                LINEAR: round(_mae_on(linear_train, val), 4),
                FOREST: round(depth_scores[str(chosen_depth)], 4),
            },
        },
        "test": test_block,
        "notes": [
            "Scores are per hour, in kWh. Each test day is scored with only earlier data.",
            "Test metrics come from models fitted on the training period. Served models are refit on training plus validation.",
            "Features exclude occupancy and session bookings, which the data does not contain.",
            "Calendar holidays and exam periods come from the synthetic calendar, not an official academic calendar.",
            "Only hours where the baseline and both models can predict are compared.",
        ],
        "data": {"laboratories": sorted(inputs.lab_names.values()), "fingerprint": fingerprint},
    }
    (out_dir / REPORT_FILE).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def predict_hours(model, rows: list[dict], ceiling_kwh: float) -> list[float]:
    """Predict hourly kWh, kept between zero and the saved ceiling so a bad extrapolation cannot pass as a forecast."""
    frame = pd.DataFrame(rows)[FEATURE_NAMES]
    return [min(max(float(v), 0.0), ceiling_kwh) for v in model.predict(frame)]
