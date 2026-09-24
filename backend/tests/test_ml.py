from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.features import FEATURE_NAMES, TelemetryTick
from app.ml_service import DelayModel


def test_shap_returns_three_named_drivers() -> None:
    model = DelayModel(ROOT / "models")
    calm = TelemetryTick(
        timestamp="2026-06-01T00:00:00+00:00",
        node_id="port-shanghai",
        weather_severity=0.12,
        port_congestion=0.18,
        carrier_reliability=0.96,
        rolling_delay_7d=4.0,
        rolling_delay_30d=5.0,
        day_of_year=40,
        disruption_event=0,
        throughput_util=0.3,
        historical_route_delay=4.0,
    )
    storm = calm.model_copy(
        update={"weather_severity": 0.95, "port_congestion": 0.92, "disruption_event": 1, "day_of_year": 200}
    )
    p_calm, d_calm = model.predict(calm)
    p_storm, d_storm = model.predict(storm)
    assert p_storm > p_calm
    assert len(d_storm) == 3
    assert {d["feature"] for d in d_storm} <= set(FEATURE_NAMES)
    assert all("shap" in d and "value" in d for d in d_storm)


if __name__ == "__main__":
    test_shap_returns_three_named_drivers()
    print("shap test OK")
