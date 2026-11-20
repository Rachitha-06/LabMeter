from datetime import date, timedelta

import pytest

from app.ml.baseline import InsufficientHistory, comparable_days, forecast_day
from app.ml.metrics import mae, rmse
from app.ml.split import split_dates
from app.services.forecasting import evaluate_baseline

MONDAY = date(2026, 7, 6)  # a Monday


# ---------- metrics ----------

def test_mae_and_rmse_on_known_values():
    pairs = [(10.0, 12.0), (5.0, 3.0), (7.0, 7.0)]  # errors 2, 2, 0
    assert mae(pairs) == pytest.approx(4 / 3)
    assert rmse(pairs) == pytest.approx((8 / 3) ** 0.5)


def test_rmse_is_never_smaller_than_mae():
    pairs = [(0.0, 1.0), (0.0, 5.0), (3.0, 3.0)]
    assert rmse(pairs) >= mae(pairs)


def test_metrics_refuse_empty_or_non_finite_input():
    with pytest.raises(ValueError):
        mae([])
    with pytest.raises(ValueError):
        rmse([(float("nan"), 1.0)])


# ---------- split ----------

def test_split_is_chronological_and_non_overlapping():
    dates = [MONDAY + timedelta(days=i) for i in range(56)]
    train, validation, test = split_dates(dates)
    assert max(train) < min(validation) < max(validation) < min(test)
    assert len(train) + len(validation) + len(test) == 56


def test_split_refuses_short_history():
    with pytest.raises(ValueError, match="at least 28 days"):
        split_dates([MONDAY + timedelta(days=i) for i in range(10)])


# ---------- baseline ----------

def series_with(days, value_fn):
    return {MONDAY + timedelta(days=i): [value_fn(MONDAY + timedelta(days=i), h) for h in range(24)]
            for i in range(days)}


def test_comparable_days_are_same_weekday_and_strictly_earlier():
    series = series_with(28, lambda d, h: 1.0)
    target = MONDAY + timedelta(days=21)  # a Monday
    days = comparable_days(series, target, k=4)
    assert days == [MONDAY + timedelta(days=w) for w in (0, 7, 14)]  # only three Mondays exist before target
    assert all(d.weekday() == 0 and d < target for d in days)


def test_forecast_is_the_mean_of_the_last_k_comparable_days():
    values = {0: 10.0, 7: 20.0, 14: 30.0, 21: 40.0}  # value by offset in days from MONDAY
    series = {MONDAY + timedelta(days=off): [v] * 24 for off, v in values.items()}
    target = MONDAY + timedelta(days=28)
    assert forecast_day(series, target, k=4)["hourly"][0] == pytest.approx(25.0)
    assert forecast_day(series, target, k=2)["hourly"][0] == pytest.approx(35.0)  # only the last two


def test_missing_hours_are_averaged_over_the_days_that_have_them():
    base = [1.0] * 24
    day0 = list(base); day0[0], day0[3] = 10.0, 5.0
    day7 = list(base); day7[0], day7[3] = None, 99.0      # no reading for hour 0 on this day
    day14 = list(base); day14[0], day14[3] = 30.0, None   # no reading for hour 3 on this day
    series = {MONDAY: day0, MONDAY + timedelta(days=7): day7, MONDAY + timedelta(days=14): day14}

    result = forecast_day(series, MONDAY + timedelta(days=21), k=3, min_history=2)
    assert result["hourly"][0] == pytest.approx((10.0 + 30.0) / 2)   # day7 is skipped for hour 0
    assert result["hourly"][3] == pytest.approx((5.0 + 99.0) / 2)    # day14 is skipped for hour 3
    assert result["missing_hours"] == []
    assert result["total_kwh"] == pytest.approx(20.0 + 52.0 + 22 * 1.0)


def test_too_little_history_is_reported_not_guessed():
    series = series_with(3, lambda d, h: 1.0)
    with pytest.raises(InsufficientHistory) as info:
        forecast_day(series, MONDAY + timedelta(days=2), k=4, min_history=2)
    assert info.value.details["comparable_days_found"] == 0


def test_forecast_never_uses_the_target_day_or_later():
    series = series_with(35, lambda d, h: float((d - MONDAY).days))
    target = MONDAY + timedelta(days=28)
    base = forecast_day(series, target, k=4)["hourly"]

    # Alter everything on and after the target day. The forecast must not change.
    changed = {d: ([999.0] * 24 if d >= target else values) for d, values in series.items()}
    assert forecast_day(changed, target, k=4)["hourly"] == base

    # Dropping future days entirely must not change it either.
    trimmed = {d: v for d, v in series.items() if d < target}
    assert forecast_day(trimmed, target, k=4)["hourly"] == base


def test_evaluation_reports_test_metrics_after_choosing_k_on_validation():
    series = series_with(56, lambda d, h: 2.0 + 0.1 * h + (d.weekday() * 0.5))  # perfectly weekly-periodic
    report = evaluate_baseline(series, "UTC")
    assert report["chosen_k"] in (1, 2, 3, 4, 6, 8)
    assert report["test"]["mae"] == pytest.approx(0.0, abs=1e-9)  # a perfectly periodic series is predicted exactly
    assert report["split"]["train"]["end"] < report["split"]["validation"]["start"]
    assert report["split"]["validation"]["end"] < report["split"]["test"]["start"]
    assert report["test"]["days_evaluated"] > 0
