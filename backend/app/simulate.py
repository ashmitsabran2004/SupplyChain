"""Hop-decaying, risk-weighted BFS cascade from a failed node."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Mapping

from pydantic import BaseModel


class WaveNode(BaseModel):
    node_id: str
    name: str
    probability_increase: float
    delay_days: float
    arrival_step: int


class SimulationResult(BaseModel):
    origin_id: str
    waves: list[list[WaveNode]]
    decay: float
    max_hops: int


def propagate(
    origin_id: str,
    names: Mapping[str, str],
    # undirected adjacency: node -> list of (neighbor, edge_predicted_risk, neighbor_congestion)
    adjacency: Mapping[str, list[tuple[str, float, float]]],
    origin_risk: float,
    decay: float = 0.62,
    max_hops: int = 5,
    origin_delay_days: float = 4.5,
) -> SimulationResult:
    if origin_id not in adjacency and origin_id not in names:
        raise KeyError(f"unknown node {origin_id}")

    waves: list[list[WaveNode]] = []
    best: dict[str, WaveNode] = {}
    origin_increase = min(0.95, max(0.35, origin_risk + 0.25))
    origin = WaveNode(
        node_id=origin_id,
        name=names.get(origin_id, origin_id),
        probability_increase=round(origin_increase, 4),
        delay_days=round(origin_delay_days, 3),
        arrival_step=0,
    )
    best[origin_id] = origin
    waves.append([origin])

    q: deque[tuple[str, int, float]] = deque([(origin_id, 0, origin_increase)])
    visited_depth: dict[str, int] = {origin_id: 0}

    while q:
        node, depth, incoming = q.popleft()
        if depth >= max_hops:
            continue
        for nbr, edge_risk, cong in adjacency.get(node, []):
            hop = depth + 1
            if hop > max_hops:
                continue
            # Risk-weighted transmission: quiet edges damp out; hot edges cascade.
            trans = decay * max(0.0, edge_risk) * (0.35 + 0.65 * cong)
            increase = incoming * trans
            if increase < 0.02:
                continue
            delay_days = origin_delay_days * (increase / origin_increase) * (0.75 + 0.25 * hop / max_hops)
            candidate = WaveNode(
                node_id=nbr,
                name=names.get(nbr, nbr),
                probability_increase=round(min(0.92, increase), 4),
                delay_days=round(delay_days, 3),
                arrival_step=hop,
            )
            prev = best.get(nbr)
            if prev is not None and prev.probability_increase >= candidate.probability_increase:
                continue
            if visited_depth.get(nbr, 999) < hop and prev is not None:
                # already reached earlier with higher or equal impact
                if prev.arrival_step <= hop:
                    continue
            best[nbr] = candidate
            visited_depth[nbr] = hop
            q.append((nbr, hop, increase))

    by_step: dict[int, list[WaveNode]] = defaultdict(list)
    for node in best.values():
        by_step[node.arrival_step].append(node)
    ordered = [by_step[k] for k in sorted(by_step)]
    for wave in ordered:
        wave.sort(key=lambda n: n.probability_increase, reverse=True)
    return SimulationResult(origin_id=origin_id, waves=ordered, decay=decay, max_hops=max_hops)
