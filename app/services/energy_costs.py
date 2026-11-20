"""Electricity cost and emissions estimates. Pure rules; the database is read by the caller.

Cost for each hour = kWh in that hour x the rate of the tariff band that covers that hour.
Emissions for each hour = kWh in that hour x the emission factor in force on that day.

An hour with no covering tariff band (or no factor) is counted as uncosted (or unfactored). It is never
filled in with a guessed rate. Taxes, fixed charges, demand charges and tariff surcharges are not modelled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional

ALL_WEEKDAYS = frozenset(range(7))
RATE_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True)
class BandSpec:
    rate_per_kwh: Decimal
    currency: str
    effective_from: date
    effective_to: Optional[date]
    weekdays: frozenset  # 0 = Monday
    start_hour: int      # inclusive, local
    end_hour: int        # exclusive, local (24 means midnight)
    band_name: Optional[str] = None


@dataclass(frozen=True)
class FactorSpec:
    value: Decimal
    unit: str
    effective_from: date
    effective_to: Optional[date]
    source: str


def parse_weekdays(text: Optional[str]) -> frozenset:
    if not text:
        return ALL_WEEKDAYS
    return frozenset(int(part) for part in text.split(",") if part.strip() != "")


def format_weekdays(days: Optional[Iterable[int]]) -> Optional[str]:
    if days is None:
        return None
    ordered = sorted(set(days))
    if ordered == list(range(7)):
        return None
    return ",".join(str(d) for d in ordered)


def _active(effective_from: date, effective_to: Optional[date], day: date) -> bool:
    return effective_from <= day and (effective_to is None or day <= effective_to)


def rate_for(bands: Iterable[BandSpec], day: date, hour: int) -> Optional[Decimal]:
    """The rate for a local day and hour, or None when no band covers it."""
    for band in bands:
        if (_active(band.effective_from, band.effective_to, day)
                and day.weekday() in band.weekdays
                and band.start_hour <= hour < band.end_hour):
            return band.rate_per_kwh
    return None


def factor_for(factors: Iterable[FactorSpec], day: date) -> Optional[FactorSpec]:
    for factor in factors:
        if _active(factor.effective_from, factor.effective_to, day):
            return factor
    return None


def bands_overlap(a: BandSpec, b: BandSpec) -> bool:
    dates = a.effective_from <= (b.effective_to or date.max) and b.effective_from <= (a.effective_to or date.max)
    days = bool(a.weekdays & b.weekdays)
    hours = a.start_hour < b.end_hour and b.start_hour < a.end_hour
    return dates and days and hours


@dataclass
class DayEstimate:
    day: date
    kwh: Decimal = Decimal("0")
    cost: Decimal = Decimal("0")
    kwh_costed: Decimal = Decimal("0")
    kwh_uncosted: Decimal = Decimal("0")
    emissions: Decimal = Decimal("0")
    kwh_unfactored: Decimal = Decimal("0")
    kwh_by_type: dict = field(default_factory=dict)
    cost_by_type: dict = field(default_factory=dict)


def estimate(hours: Iterable[tuple[date, int, Decimal, str]], bands: list[BandSpec],
             factors: list[FactorSpec]) -> dict[date, DayEstimate]:
    """hours: (local_day, local_hour, kwh, reading_type) for every reading in the period."""
    days: dict[date, DayEstimate] = {}
    for day, hour, kwh, reading_type in hours:
        entry = days.setdefault(day, DayEstimate(day=day))
        entry.kwh += kwh
        entry.kwh_by_type[reading_type] = entry.kwh_by_type.get(reading_type, Decimal("0")) + kwh

        rate = rate_for(bands, day, hour)
        if rate is None:
            entry.kwh_uncosted += kwh
        else:
            cost = (kwh * rate).quantize(RATE_QUANTUM)
            entry.kwh_costed += kwh
            entry.cost += cost
            entry.cost_by_type[reading_type] = entry.cost_by_type.get(reading_type, Decimal("0")) + cost

        factor = factor_for(factors, day)
        if factor is None:
            entry.kwh_unfactored += kwh
        else:
            entry.emissions += kwh * factor.value
    return days
