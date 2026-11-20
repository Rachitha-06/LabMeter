"""Response models. Energy values are returned as strings to avoid float rounding."""
from __future__ import annotations

from datetime import datetime, time, date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.time import as_utc


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LabOut(_Out):
    id: int
    name: str
    building: str
    lab_type: str
    computer_count: int
    timezone: str
    created_at: Optional[datetime] = None

    @field_validator("created_at")
    @classmethod
    def _utc(cls, value):
        return as_utc(value) if value else value


class EquipmentOut(_Out):
    id: int
    lab_id: int
    equipment_type: str
    quantity: int
    rated_power_w: Optional[Decimal] = None


class ScheduleOut(_Out):
    id: int
    lab_id: int
    weekday: int
    open_time: time
    close_time: time
    valid_from: date
    valid_to: Optional[date] = None


class ReadingOut(_Out):
    id: int
    lab_id: int
    meter_id: str
    timestamp_utc: datetime
    interval_kwh: Decimal
    cumulative_kwh: Optional[Decimal] = None
    reading_type: str
    source: str
    quality_flag: Optional[str] = None
    import_batch_id: Optional[int] = None

    @field_validator("timestamp_utc")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class ReadingCreateOut(BaseModel):
    status: Literal["created", "duplicate"]
    reading: ReadingOut


class RevisionOut(_Out):
    id: int
    reading_id: int
    old_interval_kwh: Decimal
    new_interval_kwh: Decimal
    reason: str
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None


class BatchOut(_Out):
    id: int
    filename: str
    sha256: str
    rows_total: int
    rows_accepted: int
    rows_rejected: int
    status: str
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None


class UserOut(_Out):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None

    @field_validator("created_at")
    @classmethod
    def _utc(cls, value):
        return as_utc(value) if value else value


class SessionOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut
    permissions: list[str]


class MeOut(BaseModel):
    user: UserOut
    permissions: list[str]


class ReviewOut(_Out):
    id: int
    alert_id: int
    user_id: Optional[int] = None
    from_status: Optional[str] = None
    to_status: str
    comment: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("created_at")
    @classmethod
    def _utc(cls, value):
        return as_utc(value) if value else value


class TariffOut(_Out):
    id: int
    rate_per_kwh: Decimal
    currency: str
    effective_from: date
    effective_to: Optional[date] = None
    time_band: Optional[str] = None
    start_hour: int
    end_hour: int
    weekdays: Optional[str] = None
    source: str


class EmissionFactorOut(_Out):
    id: int
    value: Decimal
    unit: str
    effective_from: date
    effective_to: Optional[date] = None
    version_or_year: str
    source: str


class ForecastSummaryOut(_Out):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    lab_id: int
    model_name: str
    model_version: str
    horizon_start: datetime
    horizon_end: datetime
    predicted_kwh: Decimal
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None

    @field_validator("horizon_start", "horizon_end")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class ForecastDetailOut(ForecastSummaryOut):
    details: dict
