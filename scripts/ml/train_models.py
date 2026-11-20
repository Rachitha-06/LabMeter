#!/usr/bin/env python3
"""Train and compare the forecasting models, then save the artifacts the API serves.

Usage:
    python scripts/ml/train_models.py --out models
Outputs in --out:
    linear_regression.joblib, random_forest.joblib, metadata.json, evaluation.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import DATABASE_URL, MODEL_DIR  # noqa: E402
from app.db.session import make_engine, make_session_factory  # noqa: E402
from app.ml.training import train_and_evaluate  # noqa: E402
from app.services.forecasting import load_training_inputs  # noqa: E402


def _fmt(block: dict) -> str:
    return f"MAE {block['mae']:.4f}  RMSE {block['rmse']:.4f}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", default=DATABASE_URL)
    parser.add_argument("--out", type=Path, default=Path(MODEL_DIR))
    parser.add_argument("--n-estimators", type=int, default=200)
    args = parser.parse_args(argv)

    Session = make_session_factory(make_engine(args.db_url))
    with Session() as session:
        inputs = load_training_inputs(session)
    if not inputs.series_by_lab:
        print("No readings found. Seed the database first.", file=sys.stderr)
        return 1

    report = train_and_evaluate(inputs, args.out, n_estimators=args.n_estimators)
    test = report["test"]
    print(f"Split: train {report['split']['train']['days']} days, validation {report['split']['validation']['days']}, "
          f"test {report['split']['test']['days']} ({report['split']['test']['start']} to {report['split']['test']['end']})")
    print(f"Baseline k={report['selection']['baseline_k_chosen']} (chosen on validation)")
    print(f"Random forest max_depth={report['selection']['forest_depth_chosen']} (chosen on validation)")
    print(f"Test period, {test['hours_compared']} hours compared:")
    print(f"  baseline           {_fmt(test['baseline'])}")
    for key, label in (("linear_regression", "linear regression"), ("random_forest", "random forest")):
        print(f"  {label:<18} {_fmt(test[key])}")
        for metric in ("mae", "rmse"):
            result = test[key]["vs_baseline"][metric]
            print(f"    {metric.upper()} difference {result['difference']:+.4f} kWh, "
                  f"95% interval {result['ci95']}: {result['verdict']}")
    print(f"Artifacts written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
