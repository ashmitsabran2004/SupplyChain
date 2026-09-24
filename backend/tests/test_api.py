from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


@pytest.mark.anyio
async def test_predict_shap(client: AsyncClient) -> None:
    res = await client.post("/predict", json={"node_id": "port-shanghai", "disruption_event": 1, "weather_severity": 0.8})
    assert res.status_code == 200
    body = res.json()
    assert 0 <= body["delay_probability"] <= 1
    assert len(body["drivers"]) == 3
    assert res.headers["x-graph-backend"] in {"neo4j", "local"}


@pytest.mark.anyio
async def test_simulate_waves(client: AsyncClient) -> None:
    res = await client.post("/simulate", json={"node_id": "port-shanghai", "max_hops": 4})
    assert res.status_code == 200
    body = res.json()
    assert body["waves"][0][0]["node_id"] == "port-shanghai"
    assert body["waves"][0][0]["arrival_step"] == 0
    assert "probability_increase" in body["waves"][0][0]
    assert "delay_days" in body["waves"][0][0]


@pytest.mark.anyio
async def test_impact_graph_and_reroute(client: AsyncClient) -> None:
    imp = await client.get("/impact", params={"node_id": "port-shanghai"})
    assert imp.status_code == 200
    assert "dollars_at_risk" in imp.json()
    assert "sla_breaches" in imp.json()
    gj = await client.get("/graph")
    assert gj.status_code == 200
    assert gj.json()["type"] == "FeatureCollection"
    assert len(gj.json()["features"]) > 100
    rr = await client.post("/reroute", json={"source_id": "port-shanghai", "target_id": "port-rotterdam"})
    assert rr.status_code == 200
    body = rr.json()
    assert body["original"]["node_ids"][0] == "port-shanghai"
    assert body["alternative"]["node_ids"][-1] == "port-rotterdam"
    assert "delta_risk" in body["tradeoff"]
    assert body["identical"] == (body["original"]["node_ids"] == body["alternative"]["node_ids"])
    assert rr.headers["x-path-backend"] in {"neo4j_gds", "local"}


@pytest.mark.anyio
async def test_reroute_identical_path_is_reported(client: AsyncClient) -> None:
    rr = await client.post("/reroute", json={"source_id": "port-shanghai", "target_id": "port-shanghai"})
    assert rr.status_code == 200
    body = rr.json()
    assert body["identical"] is True
    assert body["original"]["node_ids"] == body["alternative"]["node_ids"] == ["port-shanghai"]


@pytest.mark.anyio
async def test_disruption_produces_measurable_route_tradeoffs(client: AsyncClient) -> None:
    scored = await client.post("/predict", json={"node_id": "port-shanghai", "disruption_event": 1, "weather_severity": 0.82, "port_congestion": 0.91})
    assert scored.status_code == 200
    res = await client.post("/reroute", json={"source_id": "port-shanghai", "target_id": "port-rotterdam"})
    body = res.json()
    assert body["identical"] is False
    assert body["original"]["node_ids"] != body["alternative"]["node_ids"]
    assert body["tradeoff"]["delta_cost_usd"] != 0
    assert body["tradeoff"]["delta_time_hours"] != 0
    assert body["tradeoff"]["delta_risk"] != 0
