"""Consumption totals grouped by lab-local day, week, or month.

Totals keep measured, imported, and simulated energy separate, so synthetic data is never
presented as measured consumption.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.utils.periods import bucket_key
from app.utils.time import as_utc

READING_TYPES = ("measured", "imported", "simulated")


def consumption_buckets(
    session: Session,
    *,
    start: datetime,
    end: datetime,
    granularity: str,
    lab_id: int | None = None,
    reading_type: str | None = None,
) -> list[dict]:
    query = (
        select(m.EnergyReading.lab_id, m.Laboratory.name, m.Laboratory.timezone,
               m.EnergyReading.timestamp_utc, m.EnergyReading.interval_kwh,
               m.EnergyReading.reading_type, m.EnergyReading.quality_flag)
        .join(m.Laboratory, m.Laboratory.id == m.EnergyReading.lab_id)
        .where(m.EnergyReading.timestamp_utc >= as_utc(start), m.EnergyReading.timestamp_utc < as_utc(end))
    )
    if lab_id is not None:
        query = query.where(m.EnergyReading.lab_id == lab_id)
    if reading_type is not None:
        query = query.where(m.EnergyReading.reading_type == reading_type)

    buckets: dict[tuple[int, str], dict] = {}
    for row_lab_id, lab_name, tz_name, ts, kwh, rtype, flag in session.execute(query):
        local_day = as_utc(ts).astimezone(ZoneInfo(tz_name)).date()
        period = bucket_key(local_day, granularity)
        bucket = buckets.setdefault((row_lab_id, period), {
            "period": period,
            "lab_id": row_lab_id,
            "lab_name": lab_name,
            "measured_kwh": Decimal("0"),
            "imported_kwh": Decimal("0"),
            "simulated_kwh": Decimal("0"),
            "reading_count": 0,
            "resets_flagged": 0,
        })
        bucket[f"{rtype}_kwh"] += kwh
        bucket["reading_count"] += 1
        if flag == "reset_assumed":
            bucket["resets_flagged"] += 1

    out = []
    for bucket in sorted(buckets.values(), key=lambda b: (b["period"], b["lab_name"])):
        total = sum((bucket[f"{t}_kwh"] for t in READING_TYPES), Decimal("0"))
        out.append({
            **bucket,
            **{f"{t}_kwh": str(bucket[f"{t}_kwh"]) for t in READING_TYPES},
            "total_kwh": str(total),
        })
    return out
