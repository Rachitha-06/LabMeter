from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import models as m
from app.db.base import Base
from app.db.session import make_engine

TS = datetime(2026, 10, 1, 2, 30, tzinfo=timezone.utc)


@pytest.fixture()
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s
    engine.dispose()


def make_lab(session, name="Lab A"):
    lab = m.Laboratory(name=name, building="Block A", lab_type="Teaching", computer_count=10,
                       timezone="Asia/Kolkata")
    session.add(lab)
    session.commit()
    return lab


def make_reading(lab, **overrides):
    values = dict(lab_id=lab.id, meter_id="default", timestamp_utc=TS, interval_kwh=Decimal("1.0"),
                  reading_type="measured", source="test")
    values.update(overrides)
    return m.EnergyReading(**values)


def test_valid_reading_is_stored(session):
    lab = make_lab(session)
    session.add(make_reading(lab))
    session.commit()
    assert session.scalar(select(func.count()).select_from(m.EnergyReading)) == 1


def test_duplicate_reading_for_same_lab_meter_and_time_is_rejected(session):
    lab = make_lab(session)
    session.add_all([make_reading(lab), make_reading(lab)])
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_same_timestamp_on_different_meters_is_allowed(session):
    lab = make_lab(session)
    session.add_all([make_reading(lab, meter_id="A"), make_reading(lab, meter_id="B")])
    session.commit()
    assert session.scalar(select(func.count()).select_from(m.EnergyReading)) == 2


@pytest.mark.parametrize("overrides", [
    {"interval_kwh": Decimal("-1.0")},
    {"reading_type": "guessed"},
    {"cumulative_kwh": Decimal("-5")},
])
def test_invalid_reading_values_are_rejected_by_the_database(session, overrides):
    lab = make_lab(session)
    session.add(make_reading(lab, **overrides))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_alert_status_is_constrained(session):
    lab = make_lab(session)
    session.add(m.Alert(lab_id=lab.id, period_start=TS, period_end=TS + timedelta(hours=1),
                        actual_kwh=Decimal("2"), rule_id="r1", status="confirmed"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_alert_period_must_be_positive(session):
    lab = make_lab(session)
    session.add(m.Alert(lab_id=lab.id, period_start=TS, period_end=TS, actual_kwh=Decimal("2"), rule_id="r1"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_schedule_weekday_is_constrained(session):
    lab = make_lab(session)
    from datetime import date, time
    session.add(m.OperatingSchedule(lab_id=lab.id, weekday=7, open_time=time(8), close_time=time(17),
                                    valid_from=date(2026, 7, 1)))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_user_role_is_constrained(session):
    session.add(m.User(email="x@example.com", password_hash="hash", role="root"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_deleting_a_lab_removes_its_readings(session):
    lab = make_lab(session)
    session.add(make_reading(lab))
    session.commit()
    session.delete(lab)
    session.commit()
    assert session.scalar(select(func.count()).select_from(m.EnergyReading)) == 0
