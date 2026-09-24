"""Local stand-ins for the two GDS algorithms the demo uses.

Neo4j GDS remains the production path (`seed.py` + backend GraphStore). These
implementations exist so the same math can be unit-tested without a live DB.
"""

from __future__ import annotations

import heapq
from collections import defaultdict, deque
from typing import Hashable, TypeVar

N = TypeVar("N", bound=Hashable)


def weighted_dijkstra(
    adj: dict[N, list[tuple[N, float]]],
    source: N,
    target: N,
) -> tuple[list[N], float]:
    """Weighted Dijkstra shortest path. Returns (node_list, total_weight)."""
    dist: dict[N, float] = {source: 0.0}
    prev: dict[N, N | None] = {source: None}
    heap: list[tuple[float, N]] = [(0.0, source)]
    seen: set[N] = set()
    while heap:
        cost, node = heapq.heappop(heap)
        if node in seen:
            continue
        seen.add(node)
        if node == target:
            break
        for nbr, w in adj.get(node, []):
            nxt = cost + w
            if nxt < dist.get(nbr, float("inf")):
                dist[nbr] = nxt
                prev[nbr] = node
                heapq.heappush(heap, (nxt, nbr))
    if target not in dist:
        return [], float("inf")
    path: list[N] = []
    cur: N | None = target
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    path.reverse()
    return path, dist[target]


def betweenness_centrality(adj: dict[N, list[tuple[N, float]]]) -> dict[N, float]:
    """Brandes betweenness on an undirected graph (edge weights ignored for hops)."""
    nodes = list(adj.keys())
    undirected: dict[N, set[N]] = defaultdict(set)
    for u, edges in adj.items():
        for v, _w in edges:
            undirected[u].add(v)
            undirected[v].add(u)
            if v not in undirected:
                undirected[v] = undirected.get(v, set())
    cb: dict[N, float] = {n: 0.0 for n in nodes}
    for s in nodes:
        stack: list[N] = []
        pred: dict[N, list[N]] = {n: [] for n in nodes}
        sigma: dict[N, float] = {n: 0.0 for n in nodes}
        dist: dict[N, int] = {n: -1 for n in nodes}
        sigma[s] = 1.0
        dist[s] = 0
        q: deque[N] = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in undirected[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta: dict[N, float] = {n: 0.0 for n in nodes}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                if sigma[w] == 0:
                    continue
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                cb[w] += delta[w]
    # undirected: Brandes counts each pair twice
    for n in cb:
        cb[n] /= 2.0
    return cb
