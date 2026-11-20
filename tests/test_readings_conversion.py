from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.readings import (
    INTERVAL_BASELINE, INTERVAL_GAP, INTERVAL_OK, INTERVAL_RESET,
    CumulativePoint, cumulative_to_intervals,
)

HOUR = timedelta(hours=1)
T0 = datetime(2026, 10, 1, 0, tzinfo=timezone.utc)


def points(*values, step=HOUR):
    return [CumulativePoint(T0 + index * step, Decimal(str(v))) for index, v in enumerate(values)]


def test_first_point_is_baseline_and_increases_become_intervals():
    results = cumulative_to_intervals(points(100, "101.5", "103"), HOUR)
    assert results[0].status == INTERVAL_BASELINE
    assert results[0].interval_kwh is None
    assert [r.interval_kwh for r in results[1:]] == [Decimal("1.5"), Decimal("1.5")]
    assert all(r.status == INTERVAL_OK for r in results[1:])


def test_meter_reset_uses_new_cumulative_value_and_is_flagged():
    results = cumulative_to_intervals(points(500, "502", "3"), HOUR)
    assert results[2].status == INTERVAL_RESET
    assert results[2].interval_kwh == Decimal("3")


def test_missing_interval_leaves_consumption_empty_instead_of_guessing():
    gapped = [CumulativePoint(T0, Decimal(10)), CumulativePoint(T0 + 4 * HOUR, Decimal(14))]
    results = cumulative_to_intervals(gapped, HOUR)
    assert results[1].status == INTERVAL_GAP
    assert results[1].interval_kwh is None


def test_zero_change_is_a_valid_zero_interval():
    results = cumulative_to_intervals(points(5, 5), HOUR)
    assert results[1].status == INTERVAL_OK
    assert results[1].interval_kwh == Decimal("0")


def test_unsorted_input_is_returned_in_time_order():
    results = cumulative_to_intervals(list(reversed(points(100, 101, 102))), HOUR)
    timestamps = [r.timestamp for r in results]
    assert timestamps == sorted(timestamps)


def test_duplicate_timestamps_are_rejected():
    duplicated = [CumulativePoint(T0, Decimal(1)), CumulativePoint(T0, Decimal(2))]
    with pytest.raises(ValueError, match="duplicate"):
        cumulative_to_intervals(duplicated, HOUR)


def test_naive_timestamps_are_rejected():
    naive = [CumulativePoint(datetime(2026, 10, 1), Decimal(1))]
    with pytest.raises(ValueError, match="timezone-aware"):
        cumulative_to_intervals(naive, HOUR)


def test_non_positive_step_is_rejected():
    with pytest.raises(ValueError):
        cumulative_to_intervals(points(1, 2), timedelta(0))
