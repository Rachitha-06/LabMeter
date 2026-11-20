from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.validation.schemas import LabIn, ReadingIn, ScheduleIn

BASE_READING = {
    "lab_id": 1,
    "timestamp": "2026-10-01T08:00:00+05:30",
    "value": "1.25",
    "reading_type": "measured",
    "source": "meter-csv",
}


def test_valid_reading_is_normalised_to_utc_and_kwh():
    reading = ReadingIn.model_validate(BASE_READING)
    assert reading.timestamp.utcoffset().total_seconds() == 0
    assert (reading.timestamp.hour, reading.timestamp.minute) == (2, 30)
    assert reading.interval_kwh == Decimal("1.2500")
    assert reading.meter == "default"


def test_wh_values_are_converted_to_kwh():
    reading = ReadingIn.model_validate({**BASE_READING, "value": "1500", "unit": "Wh"})
    assert reading.interval_kwh == Decimal("1.5000")


@pytest.mark.parametrize("timestamp", ["2026-10-01T08:00:00", "not-a-date"])
def test_naive_or_invalid_timestamps_are_rejected(timestamp):
    with pytest.raises(ValidationError):
        ReadingIn.model_validate({**BASE_READING, "timestamp": timestamp})


@pytest.mark.parametrize("value", ["-0.5", "NaN", "1.23456"])
def test_negative_nan_and_over_precise_values_are_rejected(value):
    with pytest.raises(ValidationError):
        ReadingIn.model_validate({**BASE_READING, "value": value})


def test_unknown_unit_is_rejected():
    with pytest.raises(ValidationError):
        ReadingIn.model_validate({**BASE_READING, "unit": "MWh"})


def test_unknown_reading_type_is_rejected():
    with pytest.raises(ValidationError):
        ReadingIn.model_validate({**BASE_READING, "reading_type": "guessed"})


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        ReadingIn.model_validate({**BASE_READING, "unexpected": 1})


def test_blank_meter_id_falls_back_to_default():
    reading = ReadingIn.model_validate({**BASE_READING, "meter_id": "   "})
    assert reading.meter == "default"


def test_lab_with_valid_timezone_is_accepted():
    lab = LabIn(name="Lab A", building="Block A", lab_type="Teaching", computer_count=30,
                timezone="Asia/Kolkata")
    assert lab.timezone == "Asia/Kolkata"


def test_lab_with_unknown_timezone_is_rejected():
    with pytest.raises(ValidationError):
        LabIn(name="Lab A", building="Block A", lab_type="Teaching", computer_count=30,
              timezone="Mars/Olympus")


def test_lab_with_blank_name_is_rejected():
    with pytest.raises(ValidationError):
        LabIn(name="   ", building="Block A", lab_type="Teaching", computer_count=30)


def test_overnight_schedule_is_rejected_with_clear_message():
    with pytest.raises(ValidationError, match="overnight schedules"):
        ScheduleIn(lab_id=1, weekday=0, open_time="22:00", close_time="02:00", valid_from="2026-07-01")


def test_schedule_with_reversed_validity_dates_is_rejected():
    with pytest.raises(ValidationError):
        ScheduleIn(lab_id=1, weekday=0, open_time="08:00", close_time="17:00",
                   valid_from="2026-07-01", valid_to="2026-06-01")


def test_schedule_weekday_out_of_range_is_rejected():
    with pytest.raises(ValidationError):
        ScheduleIn(lab_id=1, weekday=7, open_time="08:00", close_time="17:00", valid_from="2026-07-01")
