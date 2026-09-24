"""Replay historical telemetry over a WebSocket, scoring each tick."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.features import TelemetryTick
from app.graph_store import GraphStore
from app.ml_service import DelayModel
from app.telemetry import generate_history
from app.tick_store import TickStore


class StreamEngine:
    def __init__(self, store: GraphStore, model: DelayModel, ticks: TickStore, speed: float = 50.0) -> None:
        self.store = store
        self.model = model
        self.ticks = ticks
        self.speed = speed
        self._history = generate_history(days=90)
        self._by_ts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self._history:
            self._by_ts[row["timestamp"]].append(row)
        self.timestamps = sorted(self._by_ts)
        self._precompute()

    def _precompute(self) -> None:
        existing = self.ticks.timestamps()
        if existing:
            latest = existing[-1]
            self.store.bulk_update_risks(
                {row["node_id"]: float(row["delay_probability"]) for row in self.ticks.at(latest)}
            )
            self.store.update_route_risks_from_nodes()
            return
        last_map: dict[str, float] = {}
        for ts in self.timestamps:
            batch: list[tuple[str, str, float, dict[str, Any]]] = []
            last_map = {}
            for row in self._by_ts[ts]:
                tick = TelemetryTick.model_validate(row)
                proba = self.model.probability(tick)
                batch.append((ts, tick.node_id, proba, {"kind": row.get("kind"), "region": row.get("region")}))
                last_map[tick.node_id] = proba
            self.ticks.insert_many(batch)
        self.store.bulk_update_risks(last_map)
        self.store.update_route_risks_from_nodes()

    async def run(self, ws: WebSocket, speed: float | None = None) -> None:
        rate = speed if speed is not None else self.speed
        delay = max(0.05, 1.0 / max(rate, 0.1))
        await ws.send_json({"type": "meta", "timestamps": self.timestamps, "speed": rate, "backend": "neo4j" if self.store.using_neo4j else "local", "centrality_backend": self.store.centrality_backend})
        for ts in self.timestamps:
            scored = self.ticks.at(ts)
            self.store.bulk_update_risks(
                {row["node_id"]: float(row["delay_probability"]) for row in scored}
            )
            self.store.update_route_risks_from_nodes()
            await ws.send_json({"type": "tick", "timestamp": ts, "nodes": scored})
            await asyncio.sleep(delay)
        await ws.send_json({"type": "done"})
