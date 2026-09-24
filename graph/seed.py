"""Load the synthetic network into Neo4j and run GDS betweenness."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from neo4j import GraphDatabase

from network import build_network

SCHEMA_PATH = Path(__file__).parent / "cypher" / "schema.cypher"


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def seed() -> dict[str, int | float]:
    uri = _env("NEO4J_URI", "bolt://localhost:7687")
    user = _env("NEO4J_USER", "neo4j")
    password = _env("NEO4J_PASSWORD", "chainsight")
    network = build_network()
    driver = GraphDatabase.driver(uri, auth=(user, password))

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [s.strip() for s in schema.split(";") if s.strip() and not s.strip().startswith("//")]

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        for stmt in statements:
            session.run(stmt)

        session.run(
            """
            UNWIND $rows AS row
            CREATE (n:Location)
            SET n.id = row.id,
                n.name = row.name,
                n.kind = row.kind,
                n.lat = row.lat,
                n.lng = row.lng,
                n.capacity = row.capacity,
                n.avg_delay = row.avg_delay,
                n.congestion_index = row.congestion_index,
                n.region = row.region,
                n.predicted_risk = 0.15,
                n.betweenness = 0.0
            WITH n, row
            FOREACH (_ IN CASE WHEN row.kind = 'port' THEN [1] ELSE [] END | SET n:Port)
            FOREACH (_ IN CASE WHEN row.kind = 'warehouse' THEN [1] ELSE [] END | SET n:Warehouse)
            FOREACH (_ IN CASE WHEN row.kind = 'distribution_center' THEN [1] ELSE [] END | SET n:DistributionCenter)
            """,
            rows=network["locations"],
        )
        session.run(
            """
            UNWIND $rows AS row
            CREATE (c:Carrier {id: row.id, name: row.name, reliability: row.reliability, mode: row.mode})
            """,
            rows=network["carriers"],
        )
        session.run(
            """
            UNWIND $rows AS row
            MATCH (s:Location {id: row.source_id})
            MATCH (t:Location {id: row.target_id})
            MATCH (c:Carrier {id: row.carrier_id})
            CREATE (s)-[r:ROUTE {
                distance_km: row.distance_km,
                cost_usd: row.cost_usd,
                historical_delay_hours: row.historical_delay_hours,
                predicted_risk: row.predicted_risk,
                transit_hours: row.transit_hours,
                gds_weight: row.gds_weight,
                baseline_weight: row.baseline_weight,
                carrier_id: row.carrier_id
            }]->(t)
            MERGE (c)-[:SERVES]->(s)
            MERGE (c)-[:SERVES]->(t)
            """,
            rows=network["routes"],
        )

        # GDS project + betweenness
        session.run("CALL gds.graph.drop('logistics', false)")
        session.run(
            """
            CALL gds.graph.project(
              'logistics',
              'Location',
              {
                ROUTE: {
                  orientation: 'UNDIRECTED',
                properties: ['distance_km', 'cost_usd', 'historical_delay_hours', 'predicted_risk', 'gds_weight', 'baseline_weight']
                }
              }
            )
            """
        )
        session.run(
            """
            CALL gds.betweenness.write('logistics', {writeProperty: 'betweenness'})
            """
        )
        counts = session.run(
            """
            MATCH (p:Port) WITH count(p) AS ports
            MATCH (w:Warehouse) WITH ports, count(w) AS warehouses
            MATCH (d:DistributionCenter) WITH ports, warehouses, count(d) AS dcs
            MATCH (c:Carrier) WITH ports, warehouses, dcs, count(c) AS carriers
            MATCH ()-[r:ROUTE]->() WITH ports, warehouses, dcs, carriers, count(r) AS routes
            MATCH (hub:Location) WITH ports, warehouses, dcs, carriers, routes, hub
            ORDER BY hub.betweenness DESC LIMIT 1
            RETURN ports, warehouses, dcs, carriers, routes, hub.id AS top_hub, hub.betweenness AS top_betweenness
            """
        ).single()
        assert counts is not None

        # Sanity-check weighted Dijkstra between two hubs
        path = session.run(
            """
            MATCH (s:Location {id: 'port-shanghai'}), (t:Location {id: 'port-rotterdam'})
            CALL gds.shortestPath.dijkstra.stream('logistics', {
              sourceNode: s,
              targetNode: t,
              relationshipWeightProperty: 'gds_weight'
            })
            YIELD nodeIds, totalCost
            RETURN totalCost, size(nodeIds) AS hops
            """
        ).single()
        assert path is not None

    driver.close()
    meta = {
        "ports": int(counts["ports"]),
        "warehouses": int(counts["warehouses"]),
        "dcs": int(counts["dcs"]),
        "carriers": int(counts["carriers"]),
        "routes": int(counts["routes"]),
        "top_hub": str(counts["top_hub"]),
        "top_betweenness": float(counts["top_betweenness"]),
        "dijkstra_shanghai_rotterdam_cost": float(path["totalCost"]),
        "dijkstra_hops": int(path["hops"]),
    }
    print(meta)
    return meta


if __name__ == "__main__":
    try:
        seed()
    except Exception as exc:  # noqa: BLE001
        print(f"SEED_FAILED: {exc}", file=sys.stderr)
        raise
