"""Chronological train, validation, and test split by calendar day.

Shuffling time series would let future observations leak into training, so the split only ever
moves forward in time: earlier days train, later days validate, the latest days test.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable


def split_dates(
    dates: Iterable[date],
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    min_days: int = 28,
) -> tuple[list[date], list[date], list[date]]:
    ordered = sorted(set(dates))
    n = len(ordered)
    if n < min_days:
        raise ValueError(f"need at least {min_days} days of data for evaluation, found {n}")
    train_end = int(n * train_fraction)
    validation_end = int(n * (train_fraction + validation_fraction))
    train, validation, test = ordered[:train_end], ordered[train_end:validation_end], ordered[validation_end:]
    if not validation or not test:
        raise ValueError("data is too short to leave both a validation and a test period")
    return train, validation, test
