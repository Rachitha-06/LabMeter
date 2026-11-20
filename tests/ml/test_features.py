import math
from datetime import date, timedelta

import pytest

from app.ml.features import (
    FEATURE_NAMES, CalendarDay, LabContext, ScheduleEntry, build_rows, features_for_day, features_for_hour,
)

START = date(2026, 7, 6)  # a Monday
CTX = LabContext(lab_id=1, computer_count=30, rated_load_kw=2.7,
                 schedules=(ScheduleEntry(0, 9, 17, START, None),))


def series_of(days, fn):
    return {START + timedelta(days=i): [fn(START + timedelta(days=i), h) for h in range(24)] for i in range(days)}


def test_is_weekend_is_not_a_feature():
    assert "is_weekend" not in FEATURE_NAMES  # it duplicates the weekday indicators exactly


def test_lags_point_at_the_same_hour_on_earlier_days():
    series = series_of(10, lambda d, h: float((d - START).days * 100 + h))
    target = START + timedelta(days=9)
    f = features_for_hour(series, CTX, target, 14, {})
    assert f["lag_1d"] == 8 * 100 + 14
    assert f["lag_2d"] == 7 * 100 + 14
    assert f["lag_7d"] == 2 * 100 + 14
    expected_mean = sum((9 - k) * 100 + 14 for k in range(1, 8)) / 7
    assert f["mean_7d_same_hour"] == pytest.approx(expected_mean)


def test_features_never_read_the_target_day():
    series = series_of(10, lambda d, h: 1.0)
    target = START + timedelta(days=9)
    before = features_for_hour(series, CTX, target, 5, {})
    series[target] = [999.0] * 24  # change everything on the day being forecast
    after = features_for_hour(series, CTX, target, 5, {})
    assert before == after


def test_future_days_do_not_change_earlier_features():
    series = series_of(14, lambda d, h: float(d.day + h))
    day = START + timedelta(days=9)
    base = features_for_hour(series, CTX, day, 3, {})
    changed = {d: ([500.0] * 24 if d > day else v) for d, v in series.items()}
    assert features_for_hour(changed, CTX, day, 3, {}) == base


def test_calendar_and_schedule_are_read_for_the_target_day():
    series = series_of(10, lambda d, h: 1.0)
    monday = START + timedelta(days=7)  # the lab is scheduled 09:00-17:00 on Mondays
    f = features_for_hour(series, CTX, monday, 10, {monday: CalendarDay(False, True)})
    assert f["is_exam_period"] == 1 and f["is_holiday"] == 0
    assert f["scheduled_open"] == 1 and f["scheduled_hours"] == 8
    after_hours = features_for_hour(series, CTX, monday, 20, {})
    assert after_hours["scheduled_open"] == 0


def test_training_rows_need_every_required_lag():
    series = series_of(10, lambda d, h: 2.0)
    rows = build_rows(series, CTX, {}, sorted(series))
    assert rows, "expected rows once seven days of history exist"
    assert all(not math.isnan(r["mean_7d_same_hour"]) for r in rows)
    assert min(r["day"] for r in rows) >= START + timedelta(days=7)  # the first week has no 7-day lag


def test_serving_features_match_training_features_for_the_same_day():
    series = series_of(12, lambda d, h: float((d - START).days + h / 10))
    target = START + timedelta(days=10)
    serving_rows, missing = features_for_day(series, CTX, target, {})
    training_rows = {r["hour"]: r for r in build_rows(series, CTX, {}, [target])}
    assert missing == []
    for features in serving_rows:
        trained = training_rows[features["hour"]]
        assert {k: trained[k] for k in FEATURE_NAMES} == features


def test_serving_reports_hours_without_required_history():
    series = series_of(3, lambda d, h: 1.0)  # too little history for a 7-day lag
    _, missing = features_for_day(series, CTX, START + timedelta(days=2), {})
    assert len(missing) == 24
