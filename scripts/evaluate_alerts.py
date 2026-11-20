#!/usr/bin/env python3
"""Run the wastage-screening rule on stored readings and score it against the synthetic labels.

Usage:
    python scripts/evaluate_alerts.py --labels data/synthetic/anomalies.csv --out reports/alert_evaluation.json

Labels are synthetic ground truth. The output describes the rule on synthetic data, not on any campus.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATABASE_URL  # noqa: E402
from app.db.session import make_engine, make_session_factory  # noqa: E402
from app.services.alert_evaluation import evaluate_against_labels  # noqa: E402
from app.services.alerts import detect_alerts  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", default=DATABASE_URL)
    parser.add_argument("--labels", type=Path, default=Path("data/synthetic/anomalies.csv"))
    parser.add_argument("--out", type=Path, default=Path("reports/alert_evaluation.json"))
    args = parser.parse_args(argv)

    with args.labels.open(newline="", encoding="utf-8") as handle:
        labels = list(csv.DictReader(handle))

    Session = make_session_factory(make_engine(args.db_url))
    with Session() as session:
        detection = detect_alerts(session)
        report = evaluate_against_labels(session, labels)
    report = {"detection": detection, **report}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Alerts created: {detection['created']} (already recorded: {detection['already_recorded']})")
    print(f"Coverage of wastage hours: {report['coverage_of_wastage_hours']}")
    print(f"Recall: {report['recall']}  Recall on assessable hours: {report['recall_on_assessable_hours']}")
    print(f"Precision: {report['precision']}")
    print(f"False positives on legitimate periods: {report['false_positive_hours_on_legitimate_periods']}")
    print(f"False positives on data-quality periods: {report['false_positive_hours_on_data_quality_periods']}")
    for kind, row in report["by_anomaly_type"].items():
        print(f"  {kind:<28} detected {row['detected']}/{row['windows']}  assessable {row['assessable']}/{row['windows']}")
    print(f"Report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
