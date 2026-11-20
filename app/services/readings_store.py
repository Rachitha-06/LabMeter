"""Storing readings without silent overwrites.

Rules (identity = lab, meter, timestamp in UTC):
- No existing row                      -> insert ("created").
- Existing row with the same kWh       -> nothing is written ("duplicate").
- Existing row with a different kWh    -> nothing is written ("conflict"). Staff must correct it explicitly.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.services.readings import (
    INTERVAL_BASELINE, INTERVAL_GAP, INTERVAL_RESET,
    CumulativePoint, cumulative_to_intervals,
)
from app.utils.time import as_utc
from app.validation.schemas import KWH_QUANTUM, ReadingIn

Key = tuple[int, str, datetime]


def _q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(KWH_QUANTUM)


@dataclass
class StoreOutcome:
    status: str  # "created" | "duplicate" | "conflict"
    reading: Optional[m.EnergyReading]
    existing: Optional[m.EnergyReading] = None


def store_reading(session: Session, reading: ReadingIn) -> StoreOutcome:
    existing = session.scalar(
        select(m.EnergyReading).where(
            m.EnergyReading.lab_id == reading.lab_id,
            m.EnergyReading.meter_id == reading.meter,
            m.EnergyReading.timestamp_utc == reading.timestamp,
        )
    )
    if existing is not None:
        if _q(existing.interval_kwh) == reading.interval_kwh:
            return StoreOutcome("duplicate", existing, existing)
        return StoreOutcome("conflict", None, existing)

    row = m.EnergyReading(
        lab_id=reading.lab_id,
        meter_id=reading.meter,
        timestamp_utc=reading.timestamp,
        interval_kwh=reading.interval_kwh,
        reading_type=reading.reading_type,
        source=reading.source,
    )
    session.add(row)
    session.flush()
    return StoreOutcome("created", row)


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

class ImportFormatError(ValueError):
    """The file as a whole cannot be read. Individual bad rows do not raise this."""


TIMESTAMP_COLUMNS = ("timestamp", "timestamp_utc")
VALUE_COLUMNS = {"value": "interval", "interval_kwh": "interval", "cumulative_kwh": "cumulative"}
LAB_COLUMNS = ("lab_id", "lab_name")
REQUIRED_COLUMNS_TEXT = (
    "lab_id or lab_name, timestamp or timestamp_utc, value / interval_kwh / cumulative_kwh, reading_type"
)


@dataclass
class ImportReport:
    rows_total: int = 0
    accepted: int = 0
    duplicates: int = 0
    conflicts: int = 0
    rejected: int = 0
    skipped_baseline: int = 0
    skipped_gap: int = 0
    resets_flagged: int = 0
    problems: list[dict] = field(default_factory=list)
    max_problems: int = 500

    def problem(self, row: int, kind: str, reason: str, **extra) -> None:
        if len(self.problems) < self.max_problems:
            self.problems.append({"row": row, "kind": kind, "reason": reason, **extra})

    def as_dict(self) -> dict:
        return {
            "rows_total": self.rows_total,
            "accepted": self.accepted,
            "duplicates": self.duplicates,
            "conflicts": self.conflicts,
            "rejected": self.rejected,
            "skipped_baseline": self.skipped_baseline,
            "skipped_gap": self.skipped_gap,
            "resets_flagged": self.resets_flagged,
            "problems": self.problems,
        }


@dataclass
class _Candidate:
    row: int
    lab_id: int
    meter: str
    timestamp: datetime
    kwh: Decimal
    reading_type: str
    source: str
    quality_flag: Optional[str] = None
    cumulative_kwh: Optional[Decimal] = None

    @property
    def key(self) -> Key:
        return (self.lab_id, self.meter, self.timestamp)


def _resolve_columns(fieldnames: list[str]) -> tuple[str, str, str, str]:
    names = set(fieldnames)
    lab_col = next((c for c in LAB_COLUMNS if c in names), None)
    ts_col = next((c for c in TIMESTAMP_COLUMNS if c in names), None)
    value_col = next((c for c in VALUE_COLUMNS if c in names), None)
    if lab_col is None or ts_col is None or value_col is None or "reading_type" not in names:
        raise ImportFormatError(f"CSV must contain the columns: {REQUIRED_COLUMNS_TEXT}")
    return lab_col, ts_col, value_col, VALUE_COLUMNS[value_col]


def parse_csv_bytes(content: bytes, max_rows: int):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFormatError("file must be UTF-8 encoded CSV") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportFormatError("CSV has no header row")
    columns = _resolve_columns([f.strip() for f in reader.fieldnames])
    rows = []
    for row in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
        if len(rows) > max_rows:
            raise ImportFormatError(f"file has more than {max_rows} rows; split it into smaller files")
    return rows, columns


def _lab_lookup(session: Session) -> tuple[dict[int, m.Laboratory], dict[str, m.Laboratory]]:
    labs = session.scalars(select(m.Laboratory).where(m.Laboratory.archived_at.is_(None))).all()
    return {lab.id: lab for lab in labs}, {lab.name: lab for lab in labs}


def _validate_rows(rows, columns, labs_by_id, labs_by_name, report: ImportReport) -> list[_Candidate]:
    lab_col, ts_col, value_col, kind = columns
    candidates: list[_Candidate] = []
    for index, raw in enumerate(rows, start=1):
        report.rows_total += 1
        lab = None
        if lab_col == "lab_id":
            try:
                lab = labs_by_id.get(int(raw.get("lab_id", "")))
            except ValueError:
                pass
        else:
            lab = labs_by_name.get(raw.get("lab_name", ""))
        if lab is None:
            report.rejected += 1
            report.problem(index, "rejected", f"unknown or archived laboratory '{raw.get(lab_col, '')}'")
            continue
        try:
            reading = ReadingIn.model_validate({
                "lab_id": lab.id,
                "meter_id": raw.get("meter_id") or None,
                "timestamp": raw.get(ts_col, ""),
                "value": raw.get(value_col, ""),
                "unit": raw.get("unit") or "kWh",
                "reading_type": raw.get("reading_type", ""),
                "source": raw.get("source") or "csv_import",
            })
        except ValidationError as exc:
            err = exc.errors()[0]
            report.rejected += 1
            report.problem(index, "rejected", f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}")
            continue
        candidates.append(_Candidate(
            row=index, lab_id=lab.id, meter=reading.meter, timestamp=reading.timestamp,
            kwh=reading.interval_kwh, reading_type=reading.reading_type, source=reading.source,
            cumulative_kwh=reading.interval_kwh if kind == "cumulative" else None,
        ))
    return candidates


def _derive_from_cumulative(
    session: Session, candidates: list[_Candidate], interval_step: timedelta, report: ImportReport
) -> list[_Candidate]:
    """Turn cumulative meter rows into interval rows, one meter series at a time."""
    cumulative = [c for c in candidates if c.cumulative_kwh is not None]
    intervals = [c for c in candidates if c.cumulative_kwh is None]
    if not cumulative:
        return intervals

    series: dict[tuple[int, str], list[_Candidate]] = {}
    for c in cumulative:
        series.setdefault((c.lab_id, c.meter), []).append(c)

    derived: list[_Candidate] = []
    for (lab_id, meter), items in series.items():
        items.sort(key=lambda c: c.timestamp)

        # Duplicate timestamps in a cumulative series are ambiguous, so every copy is rejected.
        seen_ts: dict[datetime, int] = {}
        for c in items:
            seen_ts[c.timestamp] = seen_ts.get(c.timestamp, 0) + 1
        clean = []
        for c in items:
            if seen_ts[c.timestamp] > 1:
                report.rejected += 1
                report.problem(c.row, "rejected", "duplicate timestamp inside this cumulative meter series")
            else:
                clean.append(c)
        if not clean:
            continue

        points: list[CumulativePoint] = []
        # Use the last stored cumulative value before this file as the starting point, if one exists.
        previous = session.scalar(
            select(m.EnergyReading)
            .where(
                m.EnergyReading.lab_id == lab_id,
                m.EnergyReading.meter_id == meter,
                m.EnergyReading.cumulative_kwh.is_not(None),
                m.EnergyReading.timestamp_utc < clean[0].timestamp,
            )
            .order_by(m.EnergyReading.timestamp_utc.desc())
            .limit(1)
        )
        baseline_ts = None
        if previous is not None:
            baseline_ts = as_utc(previous.timestamp_utc)
            points.append(CumulativePoint(baseline_ts, previous.cumulative_kwh))
        points.extend(CumulativePoint(c.timestamp, c.cumulative_kwh) for c in clean)

        by_ts = {c.timestamp: c for c in clean}
        for result in cumulative_to_intervals(points, interval_step):
            if baseline_ts is not None and result.timestamp == baseline_ts:
                continue
            candidate = by_ts[result.timestamp]
            if result.status == INTERVAL_BASELINE:
                report.skipped_baseline += 1
                report.problem(candidate.row, "baseline",
                               "first reading of this meter has no earlier value; no interval produced")
            elif result.status == INTERVAL_GAP:
                report.skipped_gap += 1
                report.problem(candidate.row, "gap",
                               "more than 1.5 intervals since the previous reading; consumption not attributed")
            else:
                if result.status == INTERVAL_RESET:
                    candidate.quality_flag = "reset_assumed"
                    report.resets_flagged += 1
                candidate.kwh = result.interval_kwh.quantize(KWH_QUANTUM)
                derived.append(candidate)
    return intervals + derived


def import_readings_csv(
    session: Session,
    content: bytes,
    filename: str,
    *,
    dry_run: bool,
    interval_minutes: int,
    max_rows: int,
    created_by: Optional[int] = None,
) -> dict:
    """Import a CSV of readings. Writes nothing when dry_run is True."""
    if interval_minutes <= 0:
        raise ImportFormatError("interval_minutes must be positive")
    rows, columns = parse_csv_bytes(content, max_rows)
    labs_by_id, labs_by_name = _lab_lookup(session)

    report = ImportReport()
    candidates = _validate_rows(rows, columns, labs_by_id, labs_by_name, report)
    candidates = _derive_from_cumulative(session, candidates, timedelta(minutes=interval_minutes), report)

    existing: dict[Key, Decimal] = {}
    if candidates:
        lab_ids = {c.lab_id for c in candidates}
        low = min(c.timestamp for c in candidates)
        high = max(c.timestamp for c in candidates)
        for lab_id, meter, ts, kwh in session.execute(
            select(m.EnergyReading.lab_id, m.EnergyReading.meter_id,
                   m.EnergyReading.timestamp_utc, m.EnergyReading.interval_kwh)
            .where(m.EnergyReading.lab_id.in_(lab_ids),
                   m.EnergyReading.timestamp_utc >= low,
                   m.EnergyReading.timestamp_utc <= high)
        ):
            existing[(lab_id, meter, as_utc(ts))] = _q(kwh)

    to_insert: list[_Candidate] = []
    seen: dict[Key, _Candidate] = {}
    for c in sorted(candidates, key=lambda c: c.row):
        if c.key in existing:
            if existing[c.key] == _q(c.kwh):
                report.duplicates += 1
            else:
                report.conflicts += 1
                report.problem(c.row, "conflict", "a different value is already stored for this reading",
                               existing_kwh=str(existing[c.key]), new_kwh=str(_q(c.kwh)))
            continue
        if c.key in seen:
            if seen[c.key].kwh == c.kwh:
                report.duplicates += 1
            else:
                report.conflicts += 1
                report.problem(c.row, "conflict", "this file gives two different values for the same reading",
                               existing_kwh=str(seen[c.key].kwh), new_kwh=str(c.kwh))
            continue
        seen[c.key] = c
        to_insert.append(c)

    report.accepted = len(to_insert)
    result = {"dry_run": dry_run, "batch_id": None, **report.as_dict()}
    if dry_run:
        return result

    batch = m.ImportBatch(
        filename=filename,
        sha256=hashlib.sha256(content).hexdigest(),
        rows_total=report.rows_total,
        rows_accepted=report.accepted,
        rows_rejected=report.rejected,
        status="complete",
        created_by=created_by,
    )
    session.add(batch)
    session.flush()
    for c in to_insert:
        session.add(m.EnergyReading(
            lab_id=c.lab_id,
            meter_id=c.meter,
            timestamp_utc=c.timestamp,
            interval_kwh=_q(c.kwh),
            cumulative_kwh=c.cumulative_kwh,
            reading_type=c.reading_type,
            source=c.source,
            quality_flag=c.quality_flag,
            import_batch_id=batch.id,
        ))
    result["batch_id"] = batch.id
    return result
