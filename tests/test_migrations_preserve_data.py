"""Upgrading an existing database must never delete its data.

SQLite rebuilds a table when a migration changes it. With foreign keys enforced, dropping the old
parent table cascades into child rows, so these tests insert real rows at the first revision, upgrade
to the head, and check that every row is still there.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db.session import make_engine

ROOT = Path(__file__).resolve().parents[1]
FIRST_REVISION = "3db6c50fa889"


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _counts(engine):
    with engine.connect() as conn:
        return {table: conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                for table in ("laboratories", "energy_readings", "alerts", "alert_reviews")}


def test_upgrade_to_head_keeps_every_row(tmp_path):
    url = f"sqlite:///{tmp_path / 'upgrade.db'}"
    cfg = _config(url)
    command.upgrade(cfg, FIRST_REVISION)
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO laboratories (id, name, building, lab_type, computer_count, timezone) "
                          "VALUES (1, 'Kept Lab', 'B', 'T', 10, 'UTC')"))
        for i in range(3):
            conn.execute(text(
                "INSERT INTO energy_readings (id, lab_id, meter_id, timestamp_utc, interval_kwh, reading_type, source) "
                f"VALUES ({i + 1}, 1, 'default', '2026-07-06 0{i}:00:00', 1.5, 'measured', 'test')"))
        conn.execute(text(
            "INSERT INTO alerts (id, lab_id, period_start, period_end, actual_kwh, expected_kwh, rule_id, status) "
            "VALUES (1, 1, '2026-07-06 17:00:00', '2026-07-06 18:00:00', 3.0, 0.5, 'unoccupied_excess_v1', 'open')"))
        conn.execute(text(
            "INSERT INTO alert_reviews (id, alert_id, from_status, to_status, comment) "
            "VALUES (1, 1, 'open', 'under_review', 'kept')"))
    before = _counts(engine)
    engine.dispose()

    command.upgrade(cfg, "head")
    engine = make_engine(url)
    after = _counts(engine)
    engine.dispose()
    assert before == {"laboratories": 1, "energy_readings": 3, "alerts": 1, "alert_reviews": 1}
    assert after == before, f"upgrade changed the data: before {before}, after {after}"
