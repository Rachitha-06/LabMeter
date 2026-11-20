#!/usr/bin/env python3
"""Load the synthetic dataset into an empty, migrated database.

Run after migrations:
    alembic upgrade head
    python scripts/seed_db.py --data data/synthetic
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Make the project root importable when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError
from sqlalchemy import func, select

from app.config import DATABASE_URL
from app.db import models as m
from app.db.session import make_engine, make_session_factory
from app.validation.schemas import LabIn, ReadingIn, ScheduleIn


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--db-url", default=DATABASE_URL)
    args = parser.parse_args(argv)
    data = args.data

    engine = make_engine(args.db_url)
    Session = make_session_factory(engine)
    readings_path = args.data / "readings.csv"

    with Session() as session, session.begin():
        if session.scalar(select(func.count()).select_from(m.Laboratory)):
            print("Database already contains laboratories. Seed an empty, migrated database.", file=sys.stderr)
            return 1

        lab_ids: dict[str, int] = {}
        for row in read_csv(args.data / "labs.csv"):
            lab_in = LabIn.model_validate({
                "name": row["name"], "building": row["building"], "lab_type": row["lab_type"],
                "computer_count": int(row["computer_count"]), "timezone": row["timezone"],
            })
            lab = m.Laboratory(**lab_in.model_dump())
            session.add(lab)
            session.flush()
            lab_ids[lab.name] = lab.id

        for row in read_csv(args.data / "schedules.csv"):
            schedule = ScheduleIn.model_validate({
                "lab_id": lab_ids[row["lab_name"]], "weekday": int(row["weekday"]),
                "open_time": row["open_time"], "close_time": row["close_time"],
                "valid_from": row["valid_from"], "valid_to": row["valid_to"] or None,
            })
            session.add(m.OperatingSchedule(**schedule.model_dump()))

        if (data / "equipment.csv").exists():
            for row in read_csv(data / "equipment.csv"):
                session.add(m.Equipment(
                    lab_id=lab_ids[row["lab_name"]],
                    equipment_type=row["equipment_type"],
                    quantity=int(row["quantity"]),
                    rated_power_w=Decimal(row["rated_power_w"]) if row["rated_power_w"] else None,
                ))

        if (data / "calendar.csv").exists():
            for row in read_csv(data / "calendar.csv"):
                session.add(m.AcademicCalendarDay(
                    day=date.fromisoformat(row["day"]),
                    is_holiday=row["is_holiday"] == "True",
                    is_exam_period=row["is_exam_period"] == "True",
                    label=row["label"] or None,
                ))

        batch = m.ImportBatch(
            filename=f"synthetic:{readings_path.name}",
            sha256=_sha256(readings_path),
            status="pending",
        )
        session.add(batch)
        session.flush()

        raw_rows = read_csv(readings_path)
        accepted = rejected = 0
        for row in raw_rows:
            try:
                reading = ReadingIn.model_validate({
                    "lab_id": lab_ids[row["lab_name"]],
                    "meter_id": row["meter_id"],
                    "timestamp": row["timestamp_utc"],
                    "value": row["interval_kwh"],
                    "unit": "kWh",
                    "reading_type": row["reading_type"],
                    "source": row["source"],
                })
            except (ValidationError, KeyError):
                rejected += 1
                continue
            session.add(m.EnergyReading(
                lab_id=reading.lab_id,
                meter_id=reading.meter,
                timestamp_utc=reading.timestamp,
                interval_kwh=reading.interval_kwh,
                reading_type=reading.reading_type,
                source=reading.source,
                import_batch_id=batch.id,
            ))
            accepted += 1

        batch.rows_total = len(raw_rows)
        batch.rows_accepted = accepted
        batch.rows_rejected = rejected
        batch.status = "complete"

    print(f"Seeded {len(lab_ids)} labs; readings accepted={accepted}, rejected={rejected}")
    return 0


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
