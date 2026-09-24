"""Operator demo: Shanghai hub failure → cascade, SHAP, dollars, reroute."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import asyncio
import argparse
import time
from urllib.parse import urlencode

API = os.environ.get("VITE_API_URL", "http://localhost:8000").rstrip("/")
HUB = "port-shanghai"
DEST = "port-rotterdam"
LAST_BACKENDS: dict[str, str] = {}


def _remember(path: str, headers: dict[str, str]) -> None:
    graph = headers.get("x-graph-backend", "unknown")
    centrality = headers.get("x-centrality-backend", "unknown")
    path_backend = headers.get("x-path-backend")
    LAST_BACKENDS[path] = f"graph={graph}, centrality={centrality}" + (f", path={path_backend}" if path_backend else "")


def _post(path: str, body: dict) -> dict:
    if os.environ.get("DEMO_IN_PROCESS") == "1":
        result, headers = _in_process("POST", path, body)
        _remember(path, headers)
        return result
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        _remember(path, dict(resp.headers))
        return json.loads(resp.read().decode())


def _get(path: str) -> dict:
    if os.environ.get("DEMO_IN_PROCESS") == "1":
        result, headers = _in_process("GET", path)
        _remember(path.split("?", 1)[0], headers)
        return result
    with urllib.request.urlopen(f"{API}{path}", timeout=60) as resp:
        _remember(path.split("?", 1)[0], dict(resp.headers))
        return json.loads(resp.read().decode())


def _in_process(method: str, path: str, body: dict | None = None) -> tuple[dict, dict[str, str]]:
    """Use ASGI directly when local networking is unavailable (for isolated checks)."""
    from httpx import ASGITransport, AsyncClient
    os.environ.setdefault("CHAINSIGHT_DISABLE_NEO4J", "1")
    from app.main import app

    async def request() -> dict:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.request(method, path, json=body)
            response.raise_for_status()
            return response.json(), dict(response.headers)

    return asyncio.run(request())


def _backend(path: str) -> str:
    return LAST_BACKENDS.get(path, "backend=unknown")


def timed_walkthrough() -> None:
    """Pace four operator-facing steps across three minutes."""
    started = time.monotonic()
    print("ChainSight · 3-minute walkthrough (timed)")

    print("\n[00:00] 1/4 · Shanghai disruption and cascade")
    pred = _post("/predict", {"node_id": HUB, "disruption_event": 1, "weather_severity": 0.82, "port_congestion": 0.91})
    print(f"  score={pred['delay_probability']:.3f} · {_backend('/predict')}")
    sim = _post("/simulate", {"node_id": HUB, "max_hops": 5, "decay": 0.78})
    print(f"  cascade={len(sim['waves'])} waves, {sum(map(len, sim['waves']))} nodes · {_backend('/simulate')}")

    time.sleep(max(0, 40 - (time.monotonic() - started)))
    print("\n[00:40] 2/4 · Explainability and dollar exposure")
    print("  SHAP top three:")
    for driver in pred["drivers"][:3]:
        print(f"    {driver['feature']}: SHAP {driver['shap']:+.5f}, value {driver['value']:.4f}")
    print(f"  {_backend('/predict')}")
    impact = _get(f"/impact?{urlencode({'node_id': HUB})}")
    print(f"  ${impact['dollars_at_risk']:,.2f} at risk; {impact['sla_breaches']:,} SLA breaches · {_backend('/impact')}")

    time.sleep(max(0, 80 - (time.monotonic() - started)))
    print("\n[01:20] 3/4 · Historical snapshot")
    history = _get("/graph")
    print(f"  history index · {_backend('/graph')}")
    stamps = history.get("timestamps", [])
    if stamps:
        snapshot = stamps[len(stamps) // 2]
        historical = _get(f"/graph?{urlencode({'at': snapshot})}")
        print(f"  timestamp={snapshot}; features={len(historical['features'])} · {_backend('/graph')}")
    else:
        print(f"  no scored historical timestamps available · {_backend('/graph')}")

    time.sleep(max(0, 125 - (time.monotonic() - started)))
    print("\n[02:05] 4/4 · Cost/time baseline vs risk-weighted route")
    routes = _post("/reroute", {"source_id": HUB, "target_id": DEST})
    print(f"  baseline={' → '.join(routes['original']['node_ids'])}")
    print(f"  risk-aware={' → '.join(routes['alternative']['node_ids'])}")
    print(f"  Δ cost=${routes['tradeoff']['delta_cost_usd']:,.2f}; Δ time={routes['tradeoff']['delta_time_hours']:.2f}h; Δ risk={routes['tradeoff']['delta_risk']:.4f}; {_backend('/reroute')}")
    time.sleep(max(0, 180 - (time.monotonic() - started)))
    print("\n[03:00] Walkthrough complete.")


def main() -> None:
    global API
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Target a running API (defaults to VITE_API_URL or localhost:8000)")
    parser.add_argument("--walkthrough", action="store_true", help="Run the timed three-minute judge walkthrough")
    args = parser.parse_args()
    if args.base_url:
        API = args.base_url.rstrip("/")
    if args.walkthrough:
        timed_walkthrough()
        return
    checks: list[tuple[str, bool]] = []
    print("1. Score Shanghai under disruption")
    pred = _post(
        "/predict",
        {
            "node_id": HUB,
            "disruption_event": 1,
            "weather_severity": 0.82,
            "port_congestion": 0.91,
        },
    )
    print(f"   delay_probability={pred['delay_probability']}")
    print("   SHAP", pred["drivers"])
    checks.append(("disruption prediction and SHAP drivers", 0.0 <= pred["delay_probability"] <= 1.0 and len(pred["drivers"]) == 3))

    print("2. Simulate cascade from Shanghai")
    sim = _post("/simulate", {"node_id": HUB, "max_hops": 5, "decay": 0.78})
    sizes = [len(w) for w in sim["waves"]]
    print(f"   waves={len(sim['waves'])} sizes={sizes}")
    print(f"   wave0={sim['waves'][0][0]['name']} +{sim['waves'][0][0]['probability_increase']}")
    checks.append(("multi-wave hub cascade", len(sim["waves"]) >= 2 and sum(sizes) > 10))

    print("3. Dollar impact / SLA")
    imp = _get(f"/impact?node_id={HUB}")
    print(f"   dollars_at_risk={imp['dollars_at_risk']} sla_breaches={imp['sla_breaches']}")
    checks.append(("dollar exposure and SLA impact", imp["dollars_at_risk"] > 0 and imp["sla_breaches"] > 0))

    print("4. Risk-aware reroute Shanghai → Rotterdam")
    rr = _post("/reroute", {"source_id": HUB, "target_id": DEST})
    print(f"   original hops={len(rr['original']['node_ids'])} risk={rr['original']['risk']}")
    print(f"   alternative hops={len(rr['alternative']['node_ids'])} risk={rr['alternative']['risk']}")
    print(f"   tradeoff={rr['tradeoff']}")
    checks.append(("baseline vs risk-weighted route comparison", rr["original"]["node_ids"][0] == HUB and rr["alternative"]["node_ids"][-1] == DEST and not rr["identical"] and all(rr["tradeoff"][key] != 0 for key in ("delta_cost_usd", "delta_time_hours", "delta_risk"))))
    print(f"   identical routes={rr['identical']} · path backend={rr['backend']}")

    print("5. GeoJSON graph")
    gj = _get("/graph")
    print(f"   features={len(gj['features'])}")
    checks.append(("synthetic graph available", len(gj["features"]) > 100))
    failed = [name for name, passed in checks if not passed]
    print("\nDemo summary")
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    if failed:
        raise RuntimeError("Demo checks failed: " + ", ".join(failed))
    print(f"PASS: all {len(checks)} demo checks passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"DEMO_FAILED: {exc}", file=sys.stderr)
        raise
