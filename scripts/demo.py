"""Operator demo: Shanghai hub failure → cascade, SHAP, dollars, reroute."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import asyncio

API = os.environ.get("VITE_API_URL", "http://localhost:8000").rstrip("/")
HUB = "port-shanghai"
DEST = "port-rotterdam"


def _post(path: str, body: dict) -> dict:
    if os.environ.get("DEMO_IN_PROCESS") == "1":
        return _in_process("POST", path, body)
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _get(path: str) -> dict:
    if os.environ.get("DEMO_IN_PROCESS") == "1":
        return _in_process("GET", path)
    with urllib.request.urlopen(f"{API}{path}", timeout=60) as resp:
        return json.loads(resp.read().decode())


def _in_process(method: str, path: str, body: dict | None = None) -> dict:
    """Use ASGI directly when local networking is unavailable (for isolated checks)."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async def request() -> dict:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.request(method, path, json=body)
            response.raise_for_status()
            return response.json()

    return asyncio.run(request())


def main() -> None:
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
