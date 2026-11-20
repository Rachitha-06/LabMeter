"""Database side of cost and emissions: loading configuration and estimating a period."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.utils.periods import bucket_key
from app.services.energy_costs import (
    BandSpec, FactorSpec, bands_overlap, estimate, format_weekdays, parse_weekdays,
)
from app.utils.time import as_utc


def load_bands(session: Session) -> list[BandSpec]:
    return [
        BandSpec(
            rate_per_kwh=Decimal(t.rate_per_kwh), currency=t.currency, effective_from=t.effective_from,
            effective_to=t.effective_to, weekdays=parse_weekdays(t.weekdays), start_hour=t.start_hour,
            end_hour=t.end_hour, band_name=t.time_band,
        )
        for t in session.scalars(select(m.Tariff).order_by(m.Tariff.effective_from, m.Tariff.start_hour)).all()
    ]


def load_factors(session: Session) -> list[FactorSpec]:
    return [
        FactorSpec(value=Decimal(f.value), unit=f.unit, effective_from=f.effective_from,
                   effective_to=f.effective_to, source=f.source)
        for f in session.scalars(select(m.EmissionFactor).order_by(m.EmissionFactor.effective_from)).all()
    ]


def find_overlapping_band(session: Session, candidate: BandSpec) -> Optional[m.Tariff]:
    for existing in session.scalars(select(m.Tariff)).all():
        spec = BandSpec(
            rate_per_kwh=Decimal(existing.rate_per_kwh), currency=existing.currency,
            effective_from=existing.effective_from, effective_to=existing.effective_to,
            weekdays=parse_weekdays(existing.weekdays), start_hour=existing.start_hour,
            end_hour=existing.end_hour,
        )
        if bands_overlap(candidate, spec):
            return existing
    return None


def find_overlapping_factor(session: Session, effective_from: date, effective_to: Optional[date]) -> Optional[m.EmissionFactor]:
    for existing in session.scalars(select(m.EmissionFactor)).all():
        ex_to = existing.effective_to or date.max
        if effective_from <= ex_to and existing.effective_from <= (effective_to or date.max):
            return existing
    return None


def period_hours(session: Session, lab_ids: list[int], start: datetime, end: datetime):
    """(local_day, local_hour, kwh, reading_type) for every reading in the period, in each lab's timezone."""
    rows = session.execute(
        select(m.EnergyReading.lab_id, m.Laboratory.timezone, m.EnergyReading.timestamp_utc,
               m.EnergyReading.interval_kwh, m.EnergyReading.reading_type)
        .join(m.Laboratory, m.Laboratory.id == m.EnergyReading.lab_id)
        .where(m.EnergyReading.lab_id.in_(lab_ids),
               m.EnergyReading.timestamp_utc >= as_utc(start),
               m.EnergyReading.timestamp_utc < as_utc(end))
    ).all()
    for _, tz_name, ts, kwh, rtype in rows:
        local = as_utc(ts).astimezone(ZoneInfo(tz_name))
        yield local.date(), local.hour, Decimal(kwh), rtype


def estimate_period(session: Session, lab_ids: list[int], start: datetime, end: datetime, granularity: str,
                    bands: Optional[list[BandSpec]] = None, factors: Optional[list[FactorSpec]] = None) -> dict:
    bands = load_bands(session) if bands is None else bands
    factors = load_factors(session) if factors is None else factors
    per_day = estimate(period_hours(session, lab_ids, start, end), bands, factors)
    currencies = sorted({b.currency for b in bands})
    units = sorted({f.unit for f in factors})
    buckets: dict[str, dict] = {}
    for day in sorted(per_day):
        entry = per_day[day]
        key = bucket_key(day, granularity)
        bucket = buckets.setdefault(key, {
            "period": key, "kwh": Decimal("0"), "cost": Decimal("0"), "kwh_costed": Decimal("0"),
            "kwh_uncosted": Decimal("0"), "emissions": Decimal("0"), "kwh_unfactored": Decimal("0"),
            "kwh_by_type": {}, "cost_by_type": {},
        })
        for field in ("kwh", "cost", "kwh_costed", "kwh_uncosted", "emissions", "kwh_unfactored"):
            bucket[field] += getattr(entry, field)
        for rtype, value in entry.kwh_by_type.items():
            bucket["kwh_by_type"][rtype] = bucket["kwh_by_type"].get(rtype, Decimal("0")) + value
        for rtype, value in entry.cost_by_type.items():
            bucket["cost_by_type"][rtype] = bucket["cost_by_type"].get(rtype, Decimal("0")) + value

    def render(bucket: dict) -> dict:
        return {
            "period": bucket["period"],
            "kwh": str(bucket["kwh"].quantize(Decimal("0.0001"))),
            "estimated_cost": str(bucket["cost"].quantize(Decimal("0.01"))),
            "kwh_with_tariff": str(bucket["kwh_costed"].quantize(Decimal("0.0001"))),
            "kwh_without_tariff": str(bucket["kwh_uncosted"].quantize(Decimal("0.0001"))),
            "estimated_emissions": str(bucket["emissions"].quantize(Decimal("0.0001"))),
            "kwh_without_factor": str(bucket["kwh_unfactored"].quantize(Decimal("0.0001"))),
            "kwh_by_reading_type": {k: str(v.quantize(Decimal("0.0001"))) for k, v in bucket["kwh_by_type"].items()},
            "cost_by_reading_type": {k: str(v.quantize(Decimal("0.01"))) for k, v in bucket["cost_by_type"].items()},
        }

    return {
        "granularity": granularity,
        "currency": currencies[0] if len(currencies) == 1 else None,
        "emission_unit": units[0] if len(units) == 1 else None,
        "tariff_bands_configured": len(bands),
        "emission_factors_configured": len(factors),
        "buckets": [render(buckets[k]) for k in sorted(buckets)],
        "total": render(_sum(buckets.values())) if buckets else None,
        "labels": {
            "cost": "Estimate from configured tariff bands. Taxes, fixed and demand charges are not included.",
            "emissions": "Estimate from configured emission factors. Factor source and dates are stored with each factor.",
            "savings": "Not calculated. Savings require before-and-after measurements.",
        },
    }


def _sum(buckets) -> dict:
    total = {"period": "total", "kwh": Decimal("0"), "cost": Decimal("0"), "kwh_costed": Decimal("0"),
             "kwh_uncosted": Decimal("0"), "emissions": Decimal("0"), "kwh_unfactored": Decimal("0"),
             "kwh_by_type": {}, "cost_by_type": {}}
    for b in buckets:
        for field in ("kwh", "cost", "kwh_costed", "kwh_uncosted", "emissions", "kwh_unfactored"):
            total[field] += b[field]
        for rtype, value in b["kwh_by_type"].items():
            total["kwh_by_type"][rtype] = total["kwh_by_type"].get(rtype, Decimal("0")) + value
        for rtype, value in b["cost_by_type"].items():
            total["cost_by_type"][rtype] = total["cost_by_type"].get(rtype, Decimal("0")) + value
    return total


def band_from_input(body) -> BandSpec:
    return BandSpec(
        rate_per_kwh=Decimal(body.rate_per_kwh), currency=body.currency, effective_from=body.effective_from,
        effective_to=body.effective_to, weekdays=parse_weekdays(format_weekdays(body.weekdays)),
        start_hour=body.start_hour, end_hour=body.end_hour, band_name=body.time_band,
    )
