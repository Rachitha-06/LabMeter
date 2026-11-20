"""Day, week and month bucketing shared by analytics and cost estimates."""
from __future__ import annotations

from datetime import date, timedelta


def bucket_key(day: date, granularity: str) -> str:
    """Label for the day, week (starting Monday) or month that a local day belongs to."""
    if granularity == "day":
        return day.isoformat()
    if granularity == "week":
        return (day - timedelta(days=day.weekday())).isoformat()
    return f"{day.year:04d}-{day.month:02d}"
