"""Shared feature engineering for training and serving — single source of truth."""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from pydantic import BaseModel, Field

FEATURE_NAMES: tuple[str, ...] = (
    "weather_severity",
    "port_congestion",
    "carrier_reliability",
    "rolling_delay_7d",
    "rolling_delay_30d",
    "season_sin",
    "season_cos",
    "disruption_event",
    "throughput_util",
    "historical_route_delay",
)

# Used to scale rolling delays into a 0–1ish range for the model.
DELAY_SCALE_HOURS = 48.0


class TelemetryTick(BaseModel):
    timestamp: str
    node_id: str
    weather_severity: float = Field(ge=0.0, le=1.5)
    port_congestion: float = Field(ge=0.0, le=1.5)
    carrier_reliability: float = Field(ge=0.0, le=1.0)
    rolling_delay_7d: float
    rolling_delay_30d: float
    day_of_year: int = Field(ge=1, le=366)
    disruption_event: int = Field(ge=0, le=1)
    throughput_util: float = Field(ge=0.0, le=1.5)
    historical_route_delay: float


class FeatureVector(BaseModel):
    names: list[str]
    values: list[float]


def seasonality(day_of_year: int) -> tuple[float, float]:
    ang = 2.0 * math.pi * (day_of_year / 365.25)
    return math.sin(ang), math.cos(ang)


def tick_to_features(tick: TelemetryTick) -> FeatureVector:
    s_sin, s_cos = seasonality(tick.day_of_year)
    values = [
        float(tick.weather_severity),
        float(tick.port_congestion),
        float(tick.carrier_reliability),
        float(tick.rolling_delay_7d) / DELAY_SCALE_HOURS,
        float(tick.rolling_delay_30d) / DELAY_SCALE_HOURS,
        float(s_sin),
        float(s_cos),
        float(tick.disruption_event),
        float(tick.throughput_util),
        float(tick.historical_route_delay) / DELAY_SCALE_HOURS,
    ]
    if len(values) != len(FEATURE_NAMES):
        raise ValueError("feature length drifted from FEATURE_NAMES")
    return FeatureVector(names=list(FEATURE_NAMES), values=values)


def mapping_to_tick(raw: Mapping[str, object]) -> TelemetryTick:
    return TelemetryTick.model_validate(raw)


def matrix(ticks: Sequence[TelemetryTick]) -> list[list[float]]:
    return [tick_to_features(t).values for t in ticks]
