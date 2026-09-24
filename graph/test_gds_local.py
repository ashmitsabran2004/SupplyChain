"""Verify local Dijkstra / betweenness used as GDS counterparts."""

from __future__ import annotations

from gds_local import betweenness_centrality, weighted_dijkstra
from network import build_network


def _adj() -> dict[str, list[tuple[str, float]]]:
    net = build_network()
    adj: dict[str, list[tuple[str, float]]] = {loc["id"]: [] for loc in net["locations"]}
    for r in net["routes"]:
        w = float(r["gds_weight"])
        adj[r["source_id"]].append((r["target_id"], w))
        adj[r["target_id"]].append((r["source_id"], w))
    return adj


def test_dijkstra_hub_corridor() -> None:
    adj = _adj()
    path, cost = weighted_dijkstra(adj, "port-shanghai", "port-rotterdam")
    assert path[0] == "port-shanghai"
    assert path[-1] == "port-rotterdam"
    assert cost < float("inf")
    assert len(path) >= 2


def test_betweenness_flags_hubs() -> None:
    adj = _adj()
    scores = betweenness_centrality(adj)
    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)[:8]
    hubish = {"port-shanghai", "port-singapore", "port-rotterdam", "port-la", "port-jebelali", "port-ny", "port-busan"}
    assert len(set(ranked) & hubish) >= 2, ranked


if __name__ == "__main__":
    test_dijkstra_hub_corridor()
    test_betweenness_flags_hubs()
    print("graph/test_gds_local.py OK")
