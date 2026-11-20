"""Input validation shared by API routes (Phase 3) and CSV import.

Units, timestamps and ranges are checked here, so every entry point applies the same rules.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

KWH_QUANTUM = Decimal("0.0001")
DEFAULT_METER = "default"


def check_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown IANA timezone: {value}") from exc
    return value


class ReadingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: int = Field(gt=0)
    meter_id: Optional[str] = Field(default=None, max_length=64)
    timestamp: datetime
    value: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    unit: Literal["kWh", "Wh"] = "kWh"
    reading_type: Literal["measured", "imported", "simulated"]
    source: str = Field(min_length=1, max_length=120)

    @field_validator("timestamp")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a UTC offset, e.g. 2026-10-01T08:00:00+05:30")
        return value.astimezone(timezone.utc)

    @field_validator("meter_id")
    @classmethod
    def _clean_meter(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @property
    def meter(self) -> str:
        return self.meter_id or DEFAULT_METER

    @property
    def interval_kwh(self) -> Decimal:
        """The kWh amount in this row. For a cumulative meter row, the caller decides what it means."""
        kwh = self.value / Decimal(1000) if self.unit == "Wh" else self.value
        return kwh.quantize(KWH_QUANTUM)


class LabIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    building: str = Field(min_length=1, max_length=120)
    lab_type: str = Field(min_length=1, max_length=60)
    computer_count: int = Field(ge=0, le=5000)
    timezone: str = Field(default="UTC", max_length=64)

    @field_validator("name", "building", "lab_type")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        return check_timezone(value)


def _whole_hour(value: time, field: str) -> time:
    if value.minute or value.second or value.microsecond:
        raise ValueError(f"{field} must be a whole hour, for example 08:00. Half-hour schedules are not supported yet")
    return value


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: int = Field(gt=0)
    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    open_time: time
    close_time: time
    valid_from: date
    valid_to: Optional[date] = None

    @field_validator("open_time")
    @classmethod
    def _open_whole(cls, value: time) -> time:
        return _whole_hour(value, "open_time")

    @field_validator("close_time")
    @classmethod
    def _close_whole(cls, value: time) -> time:
        return _whole_hour(value, "close_time")

    @model_validator(mode="after")
    def _check_hours_and_dates(self) -> "ScheduleIn":
        if self.close_time <= self.open_time:
            raise ValueError(
                "close_time must be after open_time; overnight schedules are not supported yet"
            )
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be before valid_from")
        return self


class LabPatch(BaseModel):
    """Partial update: only the fields provided are changed."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    building: Optional[str] = Field(default=None, min_length=1, max_length=120)
    lab_type: Optional[str] = Field(default=None, min_length=1, max_length=60)
    computer_count: Optional[int] = Field(default=None, ge=0, le=5000)
    timezone: Optional[str] = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else check_timezone(value)


class EquipmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_type: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=0, le=10000)
    rated_power_w: Optional[Decimal] = Field(default=None, gt=0, max_digits=10, decimal_places=2)


class ScheduleCreate(BaseModel):
    """Schedule body for a path-scoped create. The lab comes from the URL."""
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    open_time: time
    close_time: time
    valid_from: date
    valid_to: Optional[date] = None

    @field_validator("open_time")
    @classmethod
    def _open_whole(cls, value: time) -> time:
        return _whole_hour(value, "open_time")

    @field_validator("close_time")
    @classmethod
    def _close_whole(cls, value: time) -> time:
        return _whole_hour(value, "close_time")

    @model_validator(mode="after")
    def _check_hours_and_dates(self) -> "ScheduleCreate":
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be after open_time; overnight schedules are not supported yet")
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be before valid_from")
        return self


class ReadingPatch(BaseModel):
    """Only the kWh amount can be corrected, and a reason is always required."""
    model_config = ConfigDict(extra="forbid")

    interval_kwh: Decimal = Field(ge=0, max_digits=12, decimal_places=4)
    reason: str = Field(min_length=5, max_length=500)


EMAIL_MAX = 254


def normalise_email(value: str) -> str:
    value = value.strip().lower()
    local, sep, domain = value.partition("@")
    if not local or not sep or "." not in domain or len(value) > EMAIL_MAX or " " in value:
        raise ValueError("enter a valid email address")
    return value


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=EMAIL_MAX)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalise_email(value)


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=EMAIL_MAX)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "lab_manager", "staff", "evaluator"]

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalise_email(value)


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Optional[Literal["admin", "lab_manager", "staff", "evaluator"]] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=12, max_length=256)


class TariffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rate_per_kwh: Decimal = Field(ge=0, max_digits=10, decimal_places=4)
    currency: str = Field(min_length=3, max_length=8, pattern=r"^[A-Z]{3,8}$",
                          description="ISO-style currency code, for example INR")
    effective_from: date
    effective_to: Optional[date] = None
    time_band: Optional[str] = Field(default=None, max_length=32)
    start_hour: int = Field(default=0, ge=0, le=23)
    end_hour: int = Field(default=24, ge=1, le=24)
    weekdays: Optional[list[int]] = Field(default=None, description="0 = Monday; omit for every day")
    source: str = Field(min_length=5, max_length=255,
                        description="Where the rate comes from, for example the tariff order and its date")

    @model_validator(mode="after")
    def _check(self) -> "TariffIn":
        if self.end_hour <= self.start_hour:
            raise ValueError("end_hour must be after start_hour (hours are local, end is exclusive)")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be before effective_from")
        if self.weekdays is not None:
            if not self.weekdays or any(d < 0 or d > 6 for d in self.weekdays):
                raise ValueError("weekdays must be a non-empty list of 0 (Monday) to 6 (Sunday)")
        return self


class EmissionFactorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal = Field(ge=0, max_digits=10, decimal_places=6)
    unit: str = Field(min_length=3, max_length=40, description="for example kgCO2e/kWh")
    effective_from: date
    effective_to: Optional[date] = None
    version_or_year: str = Field(min_length=1, max_length=32)
    source: str = Field(min_length=5, max_length=255)

    @model_validator(mode="after")
    def _dates(self) -> "EmissionFactorIn":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be before effective_from")
        return self


class DetectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: Optional[int] = Field(default=None, gt=0)
    start: Optional[date] = None
    end: Optional[date] = None

    @model_validator(mode="after")
    def _range(self) -> "DetectIn":
        if self.start and self.end and self.end < self.start:
            raise ValueError("end must not be before start")
        return self


class AlertStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "under_review", "resolved"]
    comment: Optional[str] = Field(default=None, max_length=1000)


class AlertCommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=3, max_length=1000)


class ForecastCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: int = Field(gt=0)
    target_date: date = Field(description="Laboratory-local calendar day to forecast")
    model: Literal["baseline", "linear_regression", "random_forest"] = "baseline"
    comparable_days: int = Field(default=4, ge=1, le=8)
    min_history: int = Field(default=2, ge=1, le=8)

    @model_validator(mode="after")
    def _history_within_window(self) -> "ForecastCreate":
        if self.min_history > self.comparable_days:
            raise ValueError("min_history cannot exceed comparable_days")
        return self
