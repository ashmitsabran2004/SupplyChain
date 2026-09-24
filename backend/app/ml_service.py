"""Load persisted XGBoost model and emit probability + top-3 SHAP drivers."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import shap
import xgboost as xgb

from app.features import FEATURE_NAMES, FeatureVector, TelemetryTick, tick_to_features


class DelayModel:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir
        self.booster = xgb.XGBClassifier()
        self.booster.load_model(model_dir / "delay_xgb.json")
        names = json.loads((model_dir / "feature_names.json").read_text(encoding="utf-8"))
        if names != list(FEATURE_NAMES):
            raise RuntimeError("persisted feature names drifted from features.FEATURE_NAMES")
        self._explainer = shap.TreeExplainer(self.booster)

    def probability(self, tick: TelemetryTick) -> float:
        vec: FeatureVector = tick_to_features(tick)
        x = np.array([vec.values], dtype=np.float32)
        return float(self.booster.predict_proba(x)[0, 1])

    def predict(self, tick: TelemetryTick) -> tuple[float, list[dict[str, float | str]]]:
        vec: FeatureVector = tick_to_features(tick)
        x = np.array([vec.values], dtype=np.float32)
        proba = float(self.booster.predict_proba(x)[0, 1])
        shap_vals = np.array(self._explainer.shap_values(x)).reshape(-1)
        ranked = sorted(
            zip(FEATURE_NAMES, shap_vals.tolist(), vec.values),
            key=lambda t: abs(float(t[1])),
            reverse=True,
        )[:3]
        drivers = [
            {"feature": name, "shap": round(float(sv), 5), "value": round(float(val), 5)}
            for name, sv, val in ranked
        ]
        return proba, drivers


@lru_cache(maxsize=1)
def load_model(model_dir: str) -> DelayModel:
    return DelayModel(Path(model_dir))
