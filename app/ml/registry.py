"""Loads saved model artifacts and refuses to use them if they no longer match the feature code."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import joblib
import sklearn

from app.ml.features import FEATURE_NAMES

METADATA_FILE = "metadata.json"
REPORT_FILE = "evaluation.json"


class ModelUnavailable(Exception):
    pass


class ModelRegistry:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._cache: dict[str, object] = {}
        self._lock = threading.Lock()

    def metadata(self) -> dict:
        path = self.directory / METADATA_FILE
        if not path.exists():
            raise ModelUnavailable("no trained models found; run scripts/ml/train_models.py first")
        return json.loads(path.read_text(encoding="utf-8"))

    def report(self) -> dict:
        path = self.directory / REPORT_FILE
        if not path.exists():
            raise ModelUnavailable("no evaluation report found; run scripts/ml/train_models.py first")
        return json.loads(path.read_text(encoding="utf-8"))

    def get(self, name: str):
        """Return (model, model_metadata) for a trained model name."""
        meta = self.metadata()
        entry = meta.get("models", {}).get(name)
        if entry is None:
            raise ModelUnavailable(f"model '{name}' has not been trained")
        if entry.get("feature_names") != FEATURE_NAMES:
            raise ModelUnavailable("the feature definition changed since training; retrain the models")
        trained_with = entry.get("sklearn_version")
        if trained_with is None or trained_with.split(".")[:2] != sklearn.__version__.split(".")[:2]:
            raise ModelUnavailable(
                f"the models were trained with scikit-learn {trained_with or 'an unrecorded version'} but "
                f"{sklearn.__version__} is installed. Retrain: python scripts/ml/train_models.py --out models")
        with self._lock:
            if name not in self._cache:
                try:
                    self._cache[name] = joblib.load(self.directory / entry["file"])
                except Exception as exc:  # corrupt or incompatible file
                    raise ModelUnavailable(f"the model file for '{name}' cannot be loaded ({type(exc).__name__}). "
                                           "Retrain: python scripts/ml/train_models.py --out models") from exc
        return self._cache[name], entry
