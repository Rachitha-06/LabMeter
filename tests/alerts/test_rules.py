from datetime import date, timedelta

import pytest

from app.ml.features import CalendarDay, LabContext, ScheduleEntry
from app.services.alert_rules import MIN_EXCESS_KWH, RULE_ID, run_rule, severity_for

MONDAY = date(2026, 7, 6)
CTX = LabContext(lab_id=1, computer_count=30, rated_load_kw=2.7,
                 schedules=(ScheduleEntry(0, 9, 17, MONDAY, None),
                            ScheduleEntry(1, 9, 17, MONDAY, None),
                            ScheduleEntry(2, 9, 17, MONDAY, None),
                            ScheduleEntry(3, 9, 17, MONDAY, None),
                            ScheduleEntry(4, 9, 17, MONDAY, None)))
STANDBY = 0.3  # normal kWh in an unoccupied hour


def normal_series(days=21):
    """Every day uses STANDBY kWh per closed hour and 2 kWh per open hour."""
    series = {}
    for i in range(days):
        day = MONDAY + timedelta(days=i)
        series[day] = [2.0 if 9 <= h < 17 else STANDBY for h in range(24)]
    return series


def test_a_lab_without_schedule_is_not_screened_at_all():
    run = run_rule(normal_series(), LabContext(lab_id=9, computer_count=10, rated_load_kw=0.0, schedules=()), {})
    assert run.skipped_no_schedule is True
    assert run.candidates == []


def test_rule_id_is_stable():
    assert RULE_ID == "unoccupied_excess_v1"


def test_normal_standby_use_is_not_flagged():
    run = run_rule(normal_series(), CTX, {})
    assert run.candidates == []
    assert run.days_evaluated > 0


def test_excess_after_closing_is_flagged_as_one_period():
    series = normal_series()
    target = MONDAY + timedelta(days=14)  # a Monday with plenty of history
    for hour in (17, 18, 19):
        series[target][hour] = 3.3
    run = run_rule(series, CTX, {})
    candidates = [c for c in run.candidates if c.day == target]
    assert len(candidates) == 1
    assert candidates[0].start_hour == 17 and candidates[0].end_hour == 20
    assert candidates[0].hours == (17, 18, 19)
    assert candidates[0].excess_kwh == pytest.approx(3 * (3.3 - STANDBY), abs=1e-3)


def test_separate_excess_periods_stay_separate():
    series = normal_series()
    target = MONDAY + timedelta(days=14)
    series[target][18] = 3.0
    series[target][2] = 3.0
    candidates = [c for c in run_rule(series, CTX, {}).candidates if c.day == target]
    assert [c.hours for c in candidates] == [(2,), (18,)]


def test_exam_days_are_not_evaluated_at_all():
    series = normal_series()
    target = MONDAY + timedelta(days=14)
    series[target][19] = 5.0
    calendar = {target: CalendarDay(False, True)}
    run = run_rule(series, CTX, calendar)
    assert all(c.day != target for c in run.candidates)
    assert run.days_skipped_exam >= 1


def test_holidays_are_not_evaluated_at_all():
    series = normal_series()
    target = MONDAY + timedelta(days=14)
    series[target][19] = 5.0
    run = run_rule(series, CTX, {target: CalendarDay(True, False)})
    assert all(c.day != target for c in run.candidates)
    assert run.days_skipped_holiday >= 1


def test_a_day_with_only_one_comparable_is_not_judged():
    series = {MONDAY: [STANDBY] * 24, MONDAY + timedelta(days=7): [STANDBY] * 24}
    series[MONDAY + timedelta(days=7)][19] = 9.0
    run = run_rule(series, CTX, {})
    assert run.candidates == []
    assert run.hours_without_history >= 1


def test_missing_readings_are_counted_not_flagged():
    series = normal_series()
    target = MONDAY + timedelta(days=14)
    series[target][20] = None
    run = run_rule(series, CTX, {})
    assert all(20 not in c.hours for c in run.candidates if c.day == target)
    assert run.hours_without_reading >= 1


def test_small_excess_below_the_absolute_floor_is_ignored():
    series = normal_series()
    target = MONDAY + timedelta(days=14)
    series[target][19] = STANDBY + MIN_EXCESS_KWH - 0.1
    assert all(c.day != target for c in run_rule(series, CTX, {}).candidates)


def test_a_flagged_hour_is_not_used_as_a_later_reference():
    series = normal_series()
    first = MONDAY + timedelta(days=14)
    later = MONDAY + timedelta(days=21)
    series[first][19] = 6.0
    series[later] = [2.0 if 9 <= h < 17 else STANDBY for h in range(24)]
    series[later][19] = 6.0  # looks normal only if the earlier anomaly counts as a reference
    run = run_rule(series, CTX, {})
    flagged_days = {c.day for c in run.candidates}
    assert first in flagged_days
    assert later in flagged_days


def test_severity_reflects_how_large_the_excess_is():
    assert severity_for(0.6, 0.3) == "medium" or severity_for(0.6, 0.3) in ("low", "medium", "high")
    assert severity_for(0.6, 0.3) == "low"
    assert severity_for(1.0, 0.2) == "medium"
    assert severity_for(4.0, 0.5) == "high"
