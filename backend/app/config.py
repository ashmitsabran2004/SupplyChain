from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str = _env("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = _env("NEO4J_USER", "neo4j")
    neo4j_password: str = _env("NEO4J_PASSWORD", "chainsight")
    stream_speed: float = float(_env("STREAM_SPEED", "50"))
    model_dir: str = _env("MODEL_DIR", "models")
    data_dir: str = _env("DATA_DIR", "data")
    units_default: int = int(_env("UNITS_DEFAULT", "12000"))
    per_day_penalty_usd: float = float(_env("PER_DAY_PENALTY_USD", "85"))
    sla_delay_days_threshold: float = float(_env("SLA_DELAY_DAYS_THRESHOLD", "2.0"))


settings = Settings()
