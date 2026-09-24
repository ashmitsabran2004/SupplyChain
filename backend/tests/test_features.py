from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.features import FEATURE_NAMES, TelemetryTick, tick_to_features  # noqa: E402
from app.telemetry import generate_history  # noqa: E402


def test_feature_length_stable() -> None:
    tick = TelemetryTick(
        timestamp="2026-06-01T00:00:00+00:00",
        node_id="port-shanghai",
        weather_severity=0.4,
        port_congestion=0.5,
        carrier_reliability=0.9,
        rolling_delay_7d=12.0,
        rolling_delay_30d=10.0,
        day_of_year=152,
        disruption_event=0,
        throughput_util=0.6,
        historical_route_delay=8.0,
    )
    fv = tick_to_features(tick)
    assert fv.names == list(FEATURE_NAMES)
    assert len(fv.values) == len(FEATURE_NAMES)


def test_history_has_labels_and_disruptions() -> None:
    rows = generate_history(days=20)
    assert len(rows) > 100
    assert {r["delayed"] for r in rows} == {0, 1}
    assert any(r["disruption_event"] == 1 for r in rows)


if __name__ == "__main__":
    test_feature_length_stable()
    test_history_has_labels_and_disruptions()
    print("features tests OK")
