#!/usr/bin/env python3
"""Generate a labelled SYNTHETIC dataset for LabMeter Suite.

Every reading is marked reading_type='simulated' and source='synthetic_generator_v1'.
The data does not describe any real laboratory or campus. Anomalies are injected on purpose and
recorded in anomalies.csv as ground truth for evaluating the alert rules later.

Usage:
    python scripts/generate_synthetic_data.py --start 2026-07-06 --days 90 --seed 42 --out data/synthetic
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

GENERATOR_VERSION = "synthetic_generator_v1"
SOURCE = GENERATOR_VERSION
EXAM_EXTRA_HOURS = 2
UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class LabSpec:
    name: str
    building: str
    lab_type: str
    computers: int
    timezone: str
    schedule: dict  # weekday (0 = Monday) -> (open_hour, close_hour), local time
    idle_w: float
    active_w: float
    base_w: float  # lighting and HVAC share while open
    peak_util: float


LABS = [
    LabSpec("Programming Lab 1", "Block A", "Teaching", 60, "Asia/Kolkata",
            {0: (8, 20), 1: (8, 20), 2: (8, 20), 3: (8, 20), 4: (8, 20), 5: (9, 14)},
            idle_w=45, active_w=110, base_w=1500, peak_util=0.85),
    LabSpec("Electronics Lab", "Block B", "Teaching", 30, "Asia/Kolkata",
            {0: (9, 17), 1: (9, 17), 2: (9, 17), 3: (9, 17), 4: (9, 17), 5: (9, 13)},
            idle_w=35, active_w=90, base_w=900, peak_util=0.6),
    LabSpec("Research Computing Lab", "Block C", "Research", 24, "Asia/Kolkata",
            {0: (10, 22), 1: (10, 22), 2: (10, 22), 3: (10, 22), 4: (10, 22)},
            idle_w=60, active_w=250, base_w=1200, peak_util=0.7),
]

FIELDS_READINGS = ["lab_name", "timestamp_utc", "meter_id", "interval_kwh", "reading_type", "source"]
FIELDS_LABS = ["name", "building", "lab_type", "computer_count", "timezone"]
FIELDS_SCHEDULES = ["lab_name", "weekday", "open_time", "close_time", "valid_from", "valid_to"]
FIELDS_CALENDAR = ["day", "is_holiday", "is_exam_period", "label"]
FIELDS_EQUIPMENT = ["lab_name", "equipment_type", "quantity", "rated_power_w"]
FIELDS_ANOMALIES = ["lab_name", "start_utc", "end_utc", "anomaly_type", "suspected_category", "description"]


def build_calendar(start: date, days: int):
    """Synthetic academic calendar. Holiday and exam dates are assumptions, not official dates."""
    holidays = {date(2026, 8, 15): "Independence Day (synthetic assumption)"}
    exam_start = start + timedelta(days=round(days * 0.6))
    exam_days = {exam_start + timedelta(days=i) for i in range(10)}
    rows = []
    for i in range(days):
        day = start + timedelta(days=i)
        label = holidays.get(day, "")
        if day in exam_days and not label:
            label = "Mid-semester exam window (synthetic assumption)"
        rows.append({
            "day": day.isoformat(),
            "is_holiday": day in holidays,
            "is_exam_period": day in exam_days,
            "label": label,
        })
    return rows, holidays, exam_days


def local_dt(day: date, hour: int, tz: ZoneInfo) -> datetime:
    """Local datetime for day + hour. hour may be 24, which rolls over to the next day."""
    return datetime.combine(day, time(0), tzinfo=tz) + timedelta(hours=hour)


def utilisation(spec: LabSpec, hour: int, open_h: int, close_h: int) -> float:
    """Share of computers in use, peaking mid-session."""
    span = max(close_h - open_h, 1)
    position = min(max((hour - open_h + 0.5) / span, 0.0), 1.0)
    shape = 0.6 + 0.4 * math.sin(math.pi * position)
    return min(spec.peak_util * shape, 1.0)


def hour_energy_kwh(spec: LabSpec, rng: np.random.Generator, util: float, is_open: bool) -> float:
    if is_open:
        watts = spec.base_w + spec.computers * (util * spec.active_w + (1 - util) * spec.idle_w)
    else:
        watts = spec.base_w * 0.1 + spec.computers * spec.idle_w * 0.15
    return max(watts / 1000.0 * rng.normal(1.0, 0.04), 0.0)


def pick_anomaly_days(rng, spec, start, days, holidays, exam_days):
    eligible = []
    for i in range(days):
        day = start + timedelta(days=i)
        if day.weekday() in spec.schedule and day not in holidays and day not in exam_days:
            eligible.append(day)
    chosen = rng.choice(len(eligible), size=5, replace=False)
    picks = [eligible[int(i)] for i in chosen]
    return {"after_hours": picks[:3], "stuck": picks[3], "missing": picks[4]}


def simulate_lab(spec, start, days, rng, holidays, exam_days):
    tz = ZoneInfo(spec.timezone)
    picks = pick_anomaly_days(rng, spec, start, days, holidays, exam_days)
    readings, anomalies = [], []

    def label(day, begin_hour, end_hour, kind, category, text):
        anomalies.append({
            "lab_name": spec.name,
            "start_utc": local_dt(day, begin_hour, tz).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_utc": local_dt(day, end_hour, tz).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "anomaly_type": kind,
            "suspected_category": category,
            "description": text,
        })

    for i in range(days):
        day = start + timedelta(days=i)
        scheduled = None
        if day not in holidays and day.weekday() in spec.schedule:
            scheduled = spec.schedule[day.weekday()]
        window = scheduled
        if window and day in exam_days:
            window = (window[0], min(window[1] + EXAM_EXTRA_HOURS, 24))
            label(day, scheduled[1], window[1], "legitimate_extended_hours", "legitimate",
                  "Extended opening hours during exam window (synthetic calendar)")

        after_hours_today = day in picks["after_hours"]
        stuck_today = day == picks["stuck"]
        missing_today = day == picks["missing"]

        for hour in range(24):
            is_open = window is not None and window[0] <= hour < window[1]
            util = utilisation(spec, hour, window[0], window[1]) if is_open else 0.0
            kwh = hour_energy_kwh(spec, rng, util, is_open)

            if scheduled and after_hours_today and scheduled[1] <= hour < min(scheduled[1] + 3, 24):
                kwh += 0.5 * spec.computers * spec.active_w / 1000.0
            if stuck_today and 1 <= hour < 7:
                kwh += 0.9
            if missing_today and scheduled and scheduled[0] + 1 <= hour < min(scheduled[0] + 5, scheduled[1]):
                continue  # simulated meter outage: no row is written

            ts_utc = local_dt(day, hour, tz).astimezone(UTC)
            readings.append({
                "lab_name": spec.name,
                "timestamp_utc": ts_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "meter_id": "default",
                "interval_kwh": f"{kwh:.4f}",
                "reading_type": "simulated",
                "source": SOURCE,
            })

        if after_hours_today and scheduled:
            label(day, scheduled[1], min(scheduled[1] + 3, 24), "after_hours_leftover", "suspected_wastage",
                  "Half of the computers left running after closing (injected)")
        if stuck_today:
            label(day, 1, 7, "stuck_high_load", "suspected_wastage",
                  "Constant extra load during night hours (injected)")
        if missing_today and scheduled:
            label(day, scheduled[0] + 1, min(scheduled[0] + 5, scheduled[1]), "missing_data", "data_quality",
                  "Meter outage: no readings recorded (injected)")

    return {
        "lab": {"name": spec.name, "building": spec.building, "lab_type": spec.lab_type,
                "computer_count": spec.computers, "timezone": spec.timezone},
        "schedules": [
            {"lab_name": spec.name, "weekday": wd, "open_time": f"{o:02d}:00", "close_time": f"{c:02d}:00",
             "valid_from": start.isoformat(), "valid_to": ""}
            for wd, (o, c) in sorted(spec.schedule.items())
        ],
        "readings": readings,
        "anomalies": anomalies,
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate_dataset(start: date, days: int, seed: int, out_dir: Path) -> dict:
    if days < 14:
        raise ValueError("generate at least 14 days so anomalies can be placed on eligible weekdays")
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    calendar_rows, holidays, exam_days = build_calendar(start, days)

    labs, schedules, readings, anomalies = [], [], [], []
    for spec in LABS:
        result = simulate_lab(spec, start, days, rng, holidays, exam_days)
        labs.append(result["lab"])
        schedules.extend(result["schedules"])
        readings.extend(result["readings"])
        anomalies.extend(result["anomalies"])

    readings.sort(key=lambda r: (r["lab_name"], r["timestamp_utc"]))
    anomalies.sort(key=lambda a: (a["lab_name"], a["start_utc"]))

    write_csv(out_dir / "labs.csv", labs, FIELDS_LABS)
    write_csv(out_dir / "schedules.csv", schedules, FIELDS_SCHEDULES)
    write_csv(out_dir / "calendar.csv", calendar_rows, FIELDS_CALENDAR)
    write_csv(out_dir / "equipment.csv", [
        {"lab_name": spec.name, "equipment_type": "computer", "quantity": spec.computers,
         "rated_power_w": spec.active_w}
        for spec in LABS
    ], FIELDS_EQUIPMENT)
    write_csv(out_dir / "readings.csv", readings, FIELDS_READINGS)
    write_csv(out_dir / "anomalies.csv", anomalies, FIELDS_ANOMALIES)

    end = start + timedelta(days=days - 1)
    digest = sha256_file(out_dir / "readings.csv")
    (out_dir / "PROVENANCE.md").write_text(
        f"""# Synthetic dataset provenance

**These readings are synthetic. They do not represent any real laboratory or campus.**

- Generator: {GENERATOR_VERSION}
- Seed: {seed}
- Local dates: {start.isoformat()} to {end.isoformat()} ({days} days)
- Labs: {len(labs)} (see labs.csv)
- Readings written: {len(readings)} hourly rows, stored in UTC. Missing hours are removed on purpose.
- readings.csv sha256: {digest}

## Model assumptions
- Each computer draws idle_w when on but unused and active_w when in use.
- A base load covers lighting and HVAC while the lab is open. When closed, the base load drops to 10% and idle draw to 15%.
- Each hour has about 4% multiplicative noise.
- Holiday and exam dates are assumptions, not official academic calendar dates.
- Exam windows extend opening hours by {EXAM_EXTRA_HOURS} hours.
- No real tariff or emission factor is used anywhere in this dataset.
- equipment.csv lists computers at their active power. These are model assumptions, not measured ratings.

## Injected anomalies (anomalies.csv)
anomalies.csv is ground truth for evaluating alert rules later.
- `suspected_wastage` marks periods a rule should flag for human review. It is not confirmed wastage.
- `legitimate` and `data_quality` periods should not be reported as wastage.
""",
        encoding="utf-8",
    )
    return {"labs": len(labs), "readings": len(readings), "anomalies": len(anomalies), "sha256": digest}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 7, 6))
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("data/synthetic"))
    args = parser.parse_args(argv)
    summary = generate_dataset(args.start, args.days, args.seed, args.out)
    print(f"Wrote synthetic dataset to {args.out}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
