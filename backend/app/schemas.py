from __future__ import annotations

from pydantic import BaseModel, Field

from app.simulate import SimulationResult
from app.impact import ImpactResult


class PredictRequest(BaseModel):
    node_id: str
    weather_severity: float = 0.35
    port_congestion: float | None = None
    carrier_reliability: float = 0.9
    rolling_delay_7d: float | None = None
    rolling_delay_30d: float | None = None
    day_of_year: int = 180
    disruption_event: int = 0
    throughput_util: float | None = None
    historical_route_delay: float | None = None


class ShapDriver(BaseModel):
    feature: str
    shap: float
    value: float


class PredictResponse(BaseModel):
    node_id: str
    delay_probability: float
    drivers: list[ShapDriver]


class SimulateRequest(BaseModel):
    node_id: str
    decay: float = Field(default=0.62, gt=0.0, le=1.0)
    max_hops: int = Field(default=5, ge=1, le=10)
    at: str | None = None


class RerouteRequest(BaseModel):
    source_id: str
    target_id: str


class RouteLeg(BaseModel):
    node_id: str
    name: str
    lat: float
    lng: float


class RouteScore(BaseModel):
    node_ids: list[str]
    legs: list[RouteLeg]
    cost_usd: float
    time_hours: float
    risk: float
    gds_weight: float


class RerouteResponse(BaseModel):
    original: RouteScore
    alternative: RouteScore
    tradeoff: dict[str, float]
    identical: bool
    backend: str


class ImpactQuery(BaseModel):
    node_id: str | None = None
    units: int | None = None
    per_day_penalty_usd: float | None = None
