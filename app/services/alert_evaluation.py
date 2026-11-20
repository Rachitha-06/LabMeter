"""Scores the rule against labelled synthetic anomalies. Hour-level, using the labels in anomalies.csv.

Terms:
- Coverage: share of labelled hours the rule could assess at all (it needs two earlier comparable days).
- Recall: share of labelled suspected-wastage hours that were flagged.
- Recall on assessable hours: the same, counting only hours the rule could assess.
- Precision: share of flagged hours that fall inside a suspected-wastage label.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db import models as m
from app.services.alert_rules import RULE_ID, run_rule
from app.services.forecasting import load_calendar, load_hourly_series, load_lab_context


def _hours(start_iso: str, end_iso: str):
    start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    current = start
    while current < end:
        yield current.astimezone(timezone.utc)
        current += timedelta(hours=1)


def evaluate_against_labels(session, labels: list[dict]) -> dict:
    calendar = load_calendar(session)
    flagged: set[tuple[int, datetime]] = set()
    assessable: set[tuple[int, datetime]] = set()
    lab_ids: dict[str, int] = {}
    for lab in session.scalars(select(m.Laboratory)).all():
        lab_ids[lab.name] = lab.id
        series, _ = load_hourly_series(session, lab)
        if not series:
            continue
        run = run_rule(series, load_lab_context(session, lab), calendar)
        tz = ZoneInfo(lab.timezone)
        for finding in run.findings:
            moment = datetime.combine(finding.day, datetime.min.time(), tzinfo=tz) + timedelta(hours=finding.hour)
            assessable.add((lab.id, moment.astimezone(timezone.utc)))
            if finding.flagged:
                flagged.add((lab.id, moment.astimezone(timezone.utc)))

    labelled = {"suspected_wastage": set(), "legitimate": set(), "data_quality": set()}
    windows = []
    for row in labels:
        lab_id = lab_ids.get(row["lab_name"])
        if lab_id is None:
            continue
        hours = {(lab_id, h) for h in _hours(row["start_utc"], row["end_utc"])}
        labelled[row["suspected_category"]].update(hours)
        windows.append({"type": row["anomaly_type"], "category": row["suspected_category"], "hours": hours})

    gt = labelled["suspected_wastage"]
    true_positive = flagged & gt
    evaluable_gt = gt & assessable

    by_type: dict[str, dict] = {}
    for w in windows:
        bucket = by_type.setdefault(w["type"], {"category": w["category"], "windows": 0, "detected": 0,
                                                 "assessable": 0})
        bucket["windows"] += 1
        if any(h in flagged for h in w["hours"]):
            bucket["detected"] += 1
        if any(h in assessable for h in w["hours"]):
            bucket["assessable"] += 1

    def ratio(a, b):
        return round(a / b, 4) if b else None

    return {
        "rule": RULE_ID,
        "labelled_hours": {k: len(v) for k, v in labelled.items()},
        "flagged_hours": len(flagged),
        "assessable_hours": len(assessable),
        "coverage_of_wastage_hours": ratio(len(gt & assessable), len(gt)),
        "recall": ratio(len(true_positive), len(gt)),
        "recall_on_assessable_hours": ratio(len(true_positive), len(evaluable_gt)),
        "precision": ratio(len(true_positive), len(flagged)),
        "false_positive_hours_on_legitimate_periods": len(flagged & labelled["legitimate"]),
        "false_positive_hours_on_data_quality_periods": len(flagged & labelled["data_quality"]),
        "flagged_hours_with_no_label": len(flagged - gt - labelled["legitimate"] - labelled["data_quality"]),
        "by_anomaly_type": by_type,
        "notes": [
            "Labels are synthetic ground truth from the generator. They are not confirmed waste on any real laboratory.",
            "The rule is rule-based with fixed thresholds. Nothing was fitted to these labels.",
            "Coverage shows how much labelled wastage the rule could assess. Hours outside coverage are not judged at all.",
        ],
    }
