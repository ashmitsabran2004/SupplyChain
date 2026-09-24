"""Train the delay classifier and persist model + SHAP explainer assets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.features import FEATURE_NAMES, TelemetryTick, matrix
from app.telemetry import generate_history


def train(model_dir: Path, days: int = 90) -> dict[str, float | int]:
    model_dir.mkdir(parents=True, exist_ok=True)
    rows = generate_history(days=days)
    ticks = [TelemetryTick.model_validate(r) for r in rows]
    y = np.array([int(r["delayed"]) for r in rows], dtype=np.int32)
    x = np.array(matrix(ticks), dtype=np.float32)

    # Chronological split: last 20% of unique days held out
    n = len(rows)
    cut = int(n * 0.8)
    x_train, x_val = x[:cut], x[cut:]
    y_train, y_val = y[:cut], y[cut:]

    clf = xgb.XGBClassifier(
        n_estimators=120,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.85,
        colsample_bytree=0.9,
        min_child_weight=4,
        objective="binary:logistic",
        eval_metric="logloss",
        n_jobs=2,
        tree_method="hist",
    )
    clf.fit(x_train, y_train, eval_set=[(x_val, y_val)], verbose=False)
    pred = (clf.predict_proba(x_val)[:, 1] >= 0.5).astype(np.int32)
    acc = float((pred == y_val).mean())
    clf.save_model(model_dir / "delay_xgb.json")
    (model_dir / "feature_names.json").write_text(json.dumps(list(FEATURE_NAMES)), encoding="utf-8")
    metrics = {
        "rows": int(n),
        "val_accuracy": round(acc, 4),
        "val_positive_rate": float(y_val.mean()),
        "train_positive_rate": float(y_train.mean()),
    }
    (model_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(train(root / "models"))
