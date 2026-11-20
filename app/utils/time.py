from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime.

    SQLite drops timezone information when it returns DateTime columns. Everything stored
    in this project is UTC, so a naive value read back from the database is treated as UTC.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def require_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset, e.g. 2026-10-01T00:00:00+05:30")
    return as_utc(value)
