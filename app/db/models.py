"""SQLAlchemy models for LabMeter Suite.

Conventions:
- Timestamps are stored in UTC (timezone-aware columns).
- interval_kwh is the canonical energy quantity. Cumulative meter values are kept only for audit.
- reading_type is always set, so synthetic data can be separated from measured data.
- Constraints live in the database as well as in the validation layer.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, Time, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Laboratory(Base):
    __tablename__ = "laboratories"
    __table_args__ = (CheckConstraint("computer_count >= 0", name="ck_labs_computers_nonneg"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    building: Mapped[str] = mapped_column(String(120))
    lab_type: Mapped[str] = mapped_column(String(60))
    computer_count: Mapped[int] = mapped_column(Integer, default=0)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    equipment: Mapped[list[Equipment]] = relationship(back_populates="laboratory", cascade="all, delete-orphan")
    schedules: Mapped[list[OperatingSchedule]] = relationship(back_populates="laboratory", cascade="all, delete-orphan")
    readings: Mapped[list[EnergyReading]] = relationship(back_populates="laboratory", cascade="all, delete-orphan")


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_equipment_qty_nonneg"),
        CheckConstraint("rated_power_w IS NULL OR rated_power_w > 0", name="ck_equipment_power_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("laboratories.id", ondelete="CASCADE"), index=True)
    equipment_type: Mapped[str] = mapped_column(String(80))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    rated_power_w: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    laboratory: Mapped[Laboratory] = relationship(back_populates="equipment")


class OperatingSchedule(Base):
    """Scheduled opening hours for one weekday (0 = Monday). A missing weekday means closed."""
    __tablename__ = "operating_schedules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_schedule_weekday"),
        CheckConstraint("close_time > open_time", name="ck_schedule_hours"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_schedule_valid_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("laboratories.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    open_time: Mapped[time] = mapped_column(Time)
    close_time: Mapped[time] = mapped_column(Time)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    laboratory: Mapped[Laboratory] = relationship(back_populates="schedules")


class AcademicCalendarDay(Base):
    __tablename__ = "academic_calendar"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
    is_exam_period: Mapped[bool] = mapped_column(Boolean, default=False)
    is_semester: Mapped[bool] = mapped_column(Boolean, default=True)
    label: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)


class ImportBatch(Base):
    """Provenance for every bulk load (CSV import or synthetic seed)."""
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EnergyReading(Base):
    __tablename__ = "energy_readings"
    __table_args__ = (
        UniqueConstraint("lab_id", "meter_id", "timestamp_utc", name="uq_readings_lab_meter_ts"),
        Index("ix_readings_lab_ts", "lab_id", "timestamp_utc"),
        CheckConstraint("interval_kwh >= 0", name="ck_readings_interval_nonneg"),
        CheckConstraint("cumulative_kwh IS NULL OR cumulative_kwh >= 0", name="ck_readings_cumulative_nonneg"),
        CheckConstraint("reading_type IN ('measured', 'imported', 'simulated')", name="ck_readings_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("laboratories.id", ondelete="CASCADE"))
    meter_id: Mapped[str] = mapped_column(String(64), default="default", server_default="default")
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    interval_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    cumulative_kwh: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    reading_type: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(120))
    import_batch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    quality_flag: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # e.g. "reset_assumed"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    laboratory: Mapped[Laboratory] = relationship(back_populates="readings")
    revisions: Mapped[list[ReadingRevision]] = relationship(
        back_populates="reading", cascade="all, delete-orphan", order_by="ReadingRevision.id"
    )


class ReadingRevision(Base):
    """Audit trail for every manual correction. The original value is never lost."""
    __tablename__ = "reading_revisions"
    __table_args__ = (CheckConstraint("new_interval_kwh >= 0", name="ck_revisions_new_nonneg"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reading_id: Mapped[int] = mapped_column(ForeignKey("energy_readings.id", ondelete="CASCADE"), index=True)
    old_interval_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    new_interval_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    reason: Mapped[str] = mapped_column(Text)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    reading: Mapped[EnergyReading] = relationship(back_populates="revisions")


class Tariff(Base):
    """One time-of-use band of an electricity tariff. No values are seeded; every row needs a source.

    A band covers local hours [start_hour, end_hour) on the weekdays listed (null = every day).
    Bands must not overlap in date, weekday and hour at the same time.
    """
    __tablename__ = "tariffs"
    __table_args__ = (
        CheckConstraint("rate_per_kwh >= 0", name="ck_tariffs_rate_nonneg"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_tariffs_dates"),
        CheckConstraint("start_hour >= 0 AND end_hour <= 24 AND start_hour < end_hour", name="ck_tariffs_hours"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rate_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    currency: Mapped[str] = mapped_column(String(8))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    time_band: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    start_hour: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    end_hour: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    weekdays: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    source: Mapped[str] = mapped_column(String(255))


class EmissionFactor(Base):
    __tablename__ = "emission_factors"
    __table_args__ = (
        CheckConstraint("value >= 0", name="ck_emission_value_nonneg"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_emission_dates"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    unit: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(255))
    version_or_year: Mapped[str] = mapped_column(String(32))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'lab_manager', 'staff', 'evaluator')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ForecastRecord(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        CheckConstraint("horizon_end > horizon_start", name="ck_forecasts_horizon"),
        CheckConstraint("predicted_kwh >= 0", name="ck_forecasts_nonneg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("laboratories.id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(40))
    horizon_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    predicted_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("period_end > period_start", name="ck_alerts_period"),
        CheckConstraint("status IN ('open', 'under_review', 'resolved')", name="ck_alerts_status"),
        UniqueConstraint("lab_id", "rule_id", "period_start", name="uq_alerts_lab_rule_start"),
        Index("ix_alerts_lab_period", "lab_id", "period_start"),
        Index("ix_alerts_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("laboratories.id", ondelete="CASCADE"))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    expected_kwh: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(80))
    severity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    reviews: Mapped[list[AlertReview]] = relationship(back_populates="alert", cascade="all, delete-orphan")


class AlertReview(Base):
    __tablename__ = "alert_reviews"
    __table_args__ = (
        CheckConstraint("to_status IN ('open', 'under_review', 'resolved')", name="ck_reviews_to_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    alert: Mapped[Alert] = relationship(back_populates="reviews")


class AuthSession(Base):
    """Login session. Only a SHA-256 hash of the bearer token is stored."""
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
