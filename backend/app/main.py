from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.features import TelemetryTick
from app.graph_store import store
from app.impact import compute_impact
from app.ml_service import DelayModel, load_model
from app.schemas import (
    PredictRequest,
    PredictResponse,
    RerouteRequest,
    RerouteResponse,
    RouteScore,
    ShapDriver,
    SimulateRequest,
)
from app.simulate import propagate
from app.stream import StreamEngine
from app.tick_store import TickStore

MODEL_DIR = Path(__file__).resolve().parents[1] / settings.model_dir
DATA_DIR = Path(__file__).resolve().parents[1] / settings.data_dir

app = FastAPI(title="ChainSight", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Graph-Backend", "X-Path-Backend", "X-Centrality-Backend"],
)


@app.middleware("http")
async def backend_headers(request: Request, call_next: Any) -> Any:
    response = await call_next(request)
    response.headers["X-Graph-Backend"] = "neo4j" if store.using_neo4j else "local"
    response.headers["X-Centrality-Backend"] = store.centrality_backend
    if request.url.path == "/reroute":
        response.headers["X-Path-Backend"] = store.last_path_backend
    return response

_model: DelayModel | None = None
_ticks: TickStore | None = None
_stream: StreamEngine | None = None


def model() -> DelayModel:
    global _model
    if _model is None:
        _model = load_model(str(MODEL_DIR))
    return _model


def ticks() -> TickStore:
    global _ticks
    if _ticks is None:
        _ticks = TickStore(DATA_DIR / "ticks.sqlite")
    return _ticks


def stream() -> StreamEngine:
    global _stream
    if _stream is None:
        _stream = StreamEngine(store, model(), ticks(), speed=settings.stream_speed)
    return _stream


def _tick_from_request(req: PredictRequest) -> TelemetryTick:
    loc = store.locations[req.node_id]
    return TelemetryTick(
        timestamp="2026-07-01T00:00:00+00:00",
        node_id=req.node_id,
        weather_severity=req.weather_severity,
        port_congestion=req.port_congestion if req.port_congestion is not None else float(loc["congestion_index"]),
        carrier_reliability=req.carrier_reliability,
        rolling_delay_7d=req.rolling_delay_7d if req.rolling_delay_7d is not None else float(loc["avg_delay"]),
        rolling_delay_30d=req.rolling_delay_30d if req.rolling_delay_30d is not None else float(loc["avg_delay"]),
        day_of_year=req.day_of_year,
        disruption_event=req.disruption_event,
        throughput_util=req.throughput_util if req.throughput_util is not None else min(1.0, loc["capacity"] / 700_000),
        historical_route_delay=req.historical_route_delay
        if req.historical_route_delay is not None
        else float(loc["avg_delay"]),
    )


def _geojson_at(ts: str | None) -> dict[str, Any]:
    gj = store.geojson()
    if not ts:
        return gj
    scored = {row["node_id"]: row for row in ticks().at(ts)}
    if not scored:
        return gj
    for feat in gj["features"]:
        props = feat["properties"]
        nid = props.get("id")
        if nid in scored:
            props["predicted_risk"] = scored[nid]["delay_probability"]
            props["timestamp"] = ts
        elif props.get("source_id") in scored and props.get("target_id") in scored:
            props["predicted_risk"] = 0.5 * (scored[props["source_id"]]["delay_probability"] + scored[props["target_id"]]["delay_probability"])
            props["timestamp"] = ts
    return gj


def _risk_at(node_id: str, ts: str | None) -> float:
    if ts:
        rows = {row["node_id"]: row["delay_probability"] for row in ticks().at(ts)}
        if node_id in rows:
            return float(rows[node_id])
    return float(store.locations[node_id].get("predicted_risk", 0.2))


@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest) -> PredictResponse:
    if req.node_id not in store.locations:
        raise HTTPException(404, "unknown node")
    proba, drivers = model().predict(_tick_from_request(req))
    store.update_node_risk(req.node_id, proba)
    store.update_route_risks_from_nodes()
    return PredictResponse(
        node_id=req.node_id,
        delay_probability=round(proba, 4),
        drivers=[ShapDriver.model_validate(d) for d in drivers],
    )


@app.post("/simulate")
async def simulate(req: SimulateRequest) -> dict[str, Any]:
    if req.node_id not in store.locations:
        raise HTTPException(404, "unknown node")
    origin_risk = _risk_at(req.node_id, req.at)
    adjacency = store.sim_adjacency()
    if req.at:
        risks = {row["node_id"]: float(row["delay_probability"]) for row in ticks().at(req.at)}
        adjacency = {
            nid: [(nbr, 0.5 * (risks.get(nid, float(store.locations[nid]["predicted_risk"])) + risks.get(nbr, float(store.locations[nbr]["predicted_risk"]))), cong) for nbr, _edge, cong in links]
            for nid, links in store.sim_adjacency().items()
        }
    result = propagate(
        req.node_id,
        store.names(),
        adjacency,
        origin_risk=origin_risk,
        decay=req.decay,
        max_hops=req.max_hops,
    )
    return result.model_dump()


@app.post("/reroute", response_model=RerouteResponse)
async def reroute(req: RerouteRequest) -> RerouteResponse:
    original, alternative = store.original_and_alternative(req.source_id, req.target_id)
    tradeoff = {
        "delta_cost_usd": round(alternative["cost_usd"] - original["cost_usd"], 2),
        "delta_time_hours": round(alternative["time_hours"] - original["time_hours"], 2),
        "delta_risk": round(alternative["risk"] - original["risk"], 4),
    }
    identical = original["node_ids"] == alternative["node_ids"]
    return RerouteResponse(
        original=RouteScore.model_validate(original),
        alternative=RouteScore.model_validate(alternative),
        tradeoff=tradeoff,
        identical=identical,
        backend=store.last_path_backend,
    )


@app.get("/impact")
async def impact(
    node_id: str | None = Query(default=None),
    at: str | None = Query(default=None),
    units: int | None = Query(default=None),
    per_day_penalty_usd: float | None = Query(default=None),
) -> dict[str, Any]:
    u = units if units is not None else settings.units_default
    pen = per_day_penalty_usd if per_day_penalty_usd is not None else settings.per_day_penalty_usd
    if node_id:
        if node_id not in store.locations:
            raise HTTPException(404, "unknown node")
        p = _risk_at(node_id, at)
        return compute_impact(
            p,
            node_id=node_id,
            units=u,
            per_day_penalty_usd=pen,
            sla_threshold_days=settings.sla_delay_days_threshold,
        ).model_dump()
    dollars = 0.0
    breaches = 0
    probs: list[float] = []
    share = max(1, u // max(1, len(store.locations)))
    for loc in store.locations.values():
        p = float(loc.get("predicted_risk", 0.2))
        probs.append(p)
        r = compute_impact(p, node_id=loc["id"], units=share, per_day_penalty_usd=pen)
        dollars += r.dollars_at_risk
        breaches += r.sla_breaches
    avg_p = sum(probs) / max(1, len(probs))
    return {
        "node_id": None,
        "delay_probability": round(avg_p, 4),
        "expected_delay_days": round(6.0 * avg_p, 3),
        "units": u,
        "per_day_penalty_usd": pen,
        "dollars_at_risk": round(dollars, 2),
        "sla_breaches": breaches,
        "sla_threshold_days": settings.sla_delay_days_threshold,
    }


@app.get("/graph")
async def graph(at: str | None = Query(default=None)) -> dict[str, Any]:
    payload = _geojson_at(at)
    payload["timestamps"] = ticks().timestamps() if Path(DATA_DIR / "ticks.sqlite").exists() else []
    return payload


@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket, speed: float = Query(default=50.0)) -> None:
    await ws.accept()
    try:
        await stream().run(ws, speed=speed)
    except WebSocketDisconnect:
        return
