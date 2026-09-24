"""Synthetic telemetry with correlated delay labels and injected disruptions."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.features import TelemetryTick

# Import network generator from the sibling graph package
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "graph"))
from network import build_network  # noqa: E402


def _logit_delay(tick: TelemetryTick, rng: random.Random) -> float:
    """Latent delay probability with realistic correlations (not the served model)."""
    season_boost = 0.0
    # Boreal summer + APAC monsoon-ish via season_sin proxy on day of year
    if 150 <= tick.day_of_year <= 270:
        season_boost = 0.12
    z = (
        -4.4
        + 2.6 * tick.weather_severity
        + 2.3 * tick.port_congestion
        + 2.0 * (1.0 - tick.carrier_reliability)
        + 0.02 * tick.rolling_delay_7d
        + 0.01 * tick.rolling_delay_30d
        + 2.8 * tick.disruption_event
        + 0.7 * tick.throughput_util
        + 0.015 * tick.historical_route_delay
        + season_boost
        + rng.uniform(-0.2, 0.2)
    )
    return 1.0 / (1.0 + pow(2.718281828, -z))


def generate_history(
    days: int = 90,
    start: datetime | None = None,
    seed: int = 7,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    net = build_network()
    locations = net["locations"]
    carriers = net["carriers"]
    reliability_by_region = {
        loc["id"]: rng.choice(carriers)["reliability"] for loc in locations
    }
    start = start or datetime(2026, 6, 1, tzinfo=UTC)
    rows: list[dict[str, Any]] = []

    # Inject 4 multi-day disruption events at hub ports
    disruption_plan: dict[tuple[str, int], None] = {}
    hubs = ["port-shanghai", "port-singapore", "port-rotterdam", "port-la"]
    for hub in hubs:
        day0 = rng.randint(8, days - 12)
        for d in range(day0, day0 + rng.randint(3, 6)):
            disruption_plan[(hub, d)] = None

    roll7: dict[str, list[float]] = {loc["id"]: [] for loc in locations}
    roll30: dict[str, list[float]] = {loc["id"]: [] for loc in locations}

    for day in range(days):
        ts = start + timedelta(days=day)
        doy = ts.timetuple().tm_yday
        for loc in locations:
            nid = loc["id"]
            base_cong = float(loc["congestion_index"])
            weather = min(1.0, max(0.0, rng.gauss(0.28 + 0.15 * abs((doy - 200) / 180), 0.12)))
            if loc["region"] == "APAC" and 160 <= doy <= 250:
                weather = min(1.0, weather + 0.18)
            disruption = 1 if (nid, day) in disruption_plan else 0
            congestion = min(1.2, base_cong + 0.35 * weather + 0.4 * disruption + rng.uniform(-0.05, 0.08))
            util = min(1.2, loc["capacity"] / 700_000 + 0.25 * congestion + rng.uniform(0, 0.1))
            hist = float(loc["avg_delay"]) + rng.uniform(-3, 4)
            r7 = sum(roll7[nid][-7:]) / max(1, len(roll7[nid][-7:])) if roll7[nid] else hist
            r30 = sum(roll30[nid][-30:]) / max(1, len(roll30[nid][-30:])) if roll30[nid] else hist
            tick = TelemetryTick(
                timestamp=ts.isoformat(),
                node_id=nid,
                weather_severity=round(weather, 4),
                port_congestion=round(min(congestion, 1.0), 4),
                carrier_reliability=round(reliability_by_region[nid], 4),
                rolling_delay_7d=round(r7, 3),
                rolling_delay_30d=round(r30, 3),
                day_of_year=doy,
                disruption_event=disruption,
                throughput_util=round(min(util, 1.0), 4),
                historical_route_delay=round(max(0.0, hist), 3),
            )
            p = _logit_delay(tick, rng)
            delayed = 1 if rng.random() < p else 0
            realized = hist * (1.4 if delayed else 0.7) + (18.0 if disruption else 0.0)
            roll7[nid].append(realized)
            roll30[nid].append(realized)
            row = tick.model_dump()
            row["delayed"] = delayed
            row["realized_delay_hours"] = round(realized, 3)
            row["kind"] = loc["kind"]
            row["region"] = loc["region"]
            rows.append(row)
    return rows


def write_history(path: Path, days: int = 90) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_history(days=days)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path
