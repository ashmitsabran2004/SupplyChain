"""Compare Neo4j/GDS paths and centrality with the in-process local fallback."""

from __future__ import annotations

import sys

from app.graph_store import store
from gds_local import betweenness_centrality, weighted_dijkstra

SOURCE = "port-shanghai"
TARGET = "port-rotterdam"
TOP_N = 10


def main() -> int:
    if not store.using_neo4j or store._driver is None:
        print("SKIP: Neo4j is unreachable; parity check requires Neo4j with Graph Data Science.")
        return 0

    try:
        with store._driver.session() as session:
            gds_cent = {
                row["id"]: float(row["score"])
                for row in session.run(
                    "CALL gds.betweenness.stream('logistics') YIELD nodeId, score "
                    "RETURN gds.util.asNode(nodeId).id AS id, score"
                )
            }
        gds_original, gds_risk = store.original_and_alternative(SOURCE, TARGET)
        if store.last_path_backend != "neo4j_gds":
            raise RuntimeError("GDS Dijkstra failed; route result fell back to local")

        local_original_ids, _ = weighted_dijkstra(store._baseline_adj, SOURCE, TARGET)
        local_risk_ids, _ = weighted_dijkstra(store._weight_adj, SOURCE, TARGET)
        local_cent = betweenness_centrality(store._weight_adj)
        gds_top = sorted(gds_cent, key=lambda n: (-gds_cent[n], n))[:TOP_N]
        local_top = sorted(local_cent, key=lambda n: (-local_cent[n], n))[:TOP_N]

        pairs = [
            ("cost/time baseline route", gds_original["node_ids"], local_original_ids),
            ("risk-weighted route", gds_risk["node_ids"], local_risk_ids),
        ]
        route_match = all(left == right for _, left, right in pairs)
        critical_match = gds_top == local_top
        print("Neo4j/GDS vs local fallback parity")
        for title, gds_route, local_route in pairs:
            matches = gds_route == local_route
            print(f"{title}: {'MATCH' if matches else 'DIFFER'}")
            if not matches:
                print(f"  GDS:   {' -> '.join(gds_route)}")
                print(f"  Local: {' -> '.join(local_route)}")
        print(f"top {TOP_N} critical nodes: {'MATCH' if critical_match else 'DIFFER'}")
        if not critical_match:
            print("  GDS:  " + ", ".join(gds_top))
            print("  Local:" + ", ".join(local_top))
            print("  GDS only: " + ", ".join(n for n in gds_top if n not in local_top))
            print("  Local only: " + ", ".join(n for n in local_top if n not in gds_top))
        print(f"routes_match={route_match} critical_nodes_match={critical_match}")
        return 0 if route_match and critical_match else 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Neo4j responded, but parity queries failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if store._driver is not None:
            store._driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
