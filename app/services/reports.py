"""Energy report: one row per laboratory per local day, with totals.

Every figure comes from the same functions the dashboard uses, so a report and the screen agree.
Cost and emission columns are left empty until a tariff or factor is configured, rather than shown as zero.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.services.energy_store import estimate_period, load_bands, load_factors
from app.utils.time import as_utc

CSV_COLUMNS = [
    "laboratory", "date", "measured_kwh", "imported_kwh", "simulated_kwh", "total_kwh",
    "estimated_cost", "cost_currency", "estimated_emissions", "emission_unit",
    "kwh_without_tariff", "alerts_created", "meter_resets_flagged",
]


def _local_day(ts: datetime, tz: ZoneInfo):
    return as_utc(ts).astimezone(tz).date()


def build_energy_report(session: Session, lab_ids: list[int], start: datetime, end: datetime) -> dict:
    labs = session.scalars(select(m.Laboratory).where(m.Laboratory.id.in_(lab_ids)).order_by(m.Laboratory.name)).all()
    bands = load_bands(session)
    factors = load_factors(session)
    tariff_configured = bool(bands)
    factor_configured = bool(factors)
    rows: list[dict] = []

    for lab in labs:
        tz = ZoneInfo(lab.timezone)
        estimate = estimate_period(session, [lab.id], start, end, "day", bands=bands, factors=factors)
        alerts = Counter()
        for alert in session.scalars(select(m.Alert).where(
                m.Alert.lab_id == lab.id, m.Alert.period_start >= as_utc(start),
                m.Alert.period_start < as_utc(end))).all():
            alerts[_local_day(alert.period_start, tz).isoformat()] += 1
        resets = Counter()
        for ts, flag in session.execute(select(m.EnergyReading.timestamp_utc, m.EnergyReading.quality_flag).where(
                m.EnergyReading.lab_id == lab.id, m.EnergyReading.quality_flag.is_not(None),
                m.EnergyReading.timestamp_utc >= as_utc(start), m.EnergyReading.timestamp_utc < as_utc(end))).all():
            resets[_local_day(ts, tz).isoformat()] += 1

        for bucket in estimate["buckets"]:
            by_type = bucket["kwh_by_reading_type"]
            rows.append({
                "laboratory": lab.name,
                "date": bucket["period"],
                "measured_kwh": by_type.get("measured", "0.0000"),
                "imported_kwh": by_type.get("imported", "0.0000"),
                "simulated_kwh": by_type.get("simulated", "0.0000"),
                "total_kwh": bucket["kwh"],
                "estimated_cost": bucket["estimated_cost"] if tariff_configured else None,
                "cost_currency": (estimate["currency"] if tariff_configured else None),
                "estimated_emissions": bucket["estimated_emissions"] if factor_configured else None,
                "emission_unit": (estimate["emission_unit"] if factor_configured else None),
                "kwh_without_tariff": bucket["kwh_without_tariff"],
                "alerts_created": alerts.get(bucket["period"], 0),
                "meter_resets_flagged": resets.get(bucket["period"], 0),
            })

    simulated_total = sum(float(r["simulated_kwh"]) for r in rows)
    measured_total = sum(float(r["measured_kwh"]) for r in rows)
    notes = [
        "Days are counted in each laboratory's local time zone.",
        "Cost and emission estimates exclude taxes, fixed charges and surcharges, and no savings are calculated.",
    ]
    if simulated_total > 0:
        notes.append(f"This report includes {simulated_total:.2f} kWh of simulated readings. "
                     "Simulated values are not measured consumption.")
    if measured_total == 0 and simulated_total == 0:
        notes.append("No readings fall inside this period.")
    if not tariff_configured:
        notes.append("No tariff is configured, so cost columns are empty.")
    if not factor_configured:
        notes.append("No emission factor is configured, so emission columns are empty.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"start": as_utc(start).isoformat(), "end": as_utc(end).isoformat()},
        "laboratories": [lab.name for lab in labs],
        "tariff_configured": tariff_configured,
        "emission_factor_configured": factor_configured,
        "columns": CSV_COLUMNS,
        "rows": rows,
        "notes": notes,
    }


FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    """Stop spreadsheet programs from running a cell as a formula (CSV injection)."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def report_csv(report: dict) -> str:
    import csv
    import io
    out = io.StringIO()
    out.write(f"# LabMeter Suite energy report\n# generated_at: {report['generated_at']}\n")
    out.write(f"# period_utc: {report['period']['start']} to {report['period']['end']}\n")
    for note in report["notes"]:
        out.write(f"# note: {note}\n")
    writer = csv.DictWriter(out, fieldnames=report["columns"], lineterminator="\n")
    writer.writeheader()
    for row in report["rows"]:
        writer.writerow({k: safe_cell("" if row.get(k) is None else row.get(k)) for k in report["columns"]})
    return out.getvalue()
