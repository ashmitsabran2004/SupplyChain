"""Train + SHAP serving smoke (shared feature names)."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.features import FEATURE_NAMES, TelemetryTick
from app.ml_service import DelayModel


def test_trained_model_and_shap() -> None:
    model_dir = ROOT / "models"
    names = json.loads((model_dir / "feature_names.json").read_text())
    assert names == list(FEATURE_NAMES)
    model = DelayModel(model_dir)
    calm = TelemetryTick(
        timestamp="2026-07-01T00:00:00+00:00",
        node_id="port-shanghai",
        weather_severity=0.1,
        port_congestion=0.15,
        carrier_reliability=0.97,
        rolling_delay_7d=4.0,
        rolling_delay_30d=5.0,
        day_of_year=182,
        disruption_event=0,
        throughput_util=0.3,
        historical_route_delay=4.0,
    )
    storm = calm.model_copy(
        update={"weather_severity": 0.9, "port_congestion": 0.95, "disruption_event": 1, "rolling_delay_7d": 30.0}
    )
    p_calm, d_calm = model.predict(calm)
    p_storm, d_storm = model.predict(storm)
    assert 0.0 <= p_calm <= 1.0
    assert 0.0 <= p_storm <= 1.0
    assert p_storm > p_calm
    assert len(d_storm) == 3
    assert {d["feature"] for d in d_storm} <= set(FEATURE_NAMES)
    print({"p_calm": round(p_calm, 4), "p_storm": round(p_storm, 4), "drivers": d_storm})


if __name__ == "__main__":
    test_trained_model_and_shap()
    print("shap serving OK")
