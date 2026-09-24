"""Convert delay probability into dollars at risk and SLA breaches."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImpactResult(BaseModel):
    node_id: str | None
    delay_probability: float
    expected_delay_days: float
    units: int
    per_day_penalty_usd: float
    dollars_at_risk: float
    sla_breaches: int
    sla_threshold_days: float


def compute_impact(
    delay_probability: float,
    *,
    node_id: str | None = None,
    units: int = 12_000,
    per_day_penalty_usd: float = 85.0,
    sla_threshold_days: float = 2.0,
    expected_delay_days: float | None = None,
) -> ImpactResult:
    p = min(1.0, max(0.0, delay_probability))
    delay_days = expected_delay_days if expected_delay_days is not None else 6.0 * p
    dollars = round(units * delay_days * per_day_penalty_usd * p, 2)
    # Each unit whose expected delay exceeds SLA is a breach, scaled by probability.
    breach_frac = 0.0
    if delay_days > sla_threshold_days:
        over = (delay_days - sla_threshold_days) / max(delay_days, 1e-6)
        breach_frac = min(1.0, p * (0.35 + 0.65 * over))
    sla = int(round(units * breach_frac))
    return ImpactResult(
        node_id=node_id,
        delay_probability=round(p, 4),
        expected_delay_days=round(delay_days, 3),
        units=units,
        per_day_penalty_usd=per_day_penalty_usd,
        dollars_at_risk=dollars,
        sla_breaches=sla,
        sla_threshold_days=sla_threshold_days,
    )
