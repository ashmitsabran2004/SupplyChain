"""Network access: Neo4j when reachable, otherwise the same synthetic seed in memory."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from app.config import settings

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "graph"))
from gds_local import betweenness_centrality, weighted_dijkstra  # noqa: E402
from network import baseline_weight, build_network, gds_weight  # noqa: E402

log = logging.getLogger(__name__)


class GraphStore:
    def __init__(self) -> None:
        self.using_neo4j = False
        self.centrality_backend = "local"
        self.last_path_backend = "local"
        self._driver: Any = None
        net = build_network()
        self.locations: dict[str, dict[str, Any]] = {r["id"]: dict(r) for r in net["locations"]}
        self.carriers: dict[str, dict[str, Any]] = {r["id"]: dict(r) for r in net["carriers"]}
        self.routes: list[dict[str, Any]] = [dict(r) for r in net["routes"]]
        for loc in self.locations.values():
            loc.setdefault("predicted_risk", 0.15)
            loc.setdefault("betweenness", 0.0)
        self._rebuild_adj()
        scores = betweenness_centrality(self._weight_adj)
        mx = max(scores.values()) or 1.0
        for nid, sc in scores.items():
            if nid in self.locations:
                self.locations[nid]["betweenness"] = sc
                self.locations[nid]["betweenness_norm"] = sc / mx
        try:
            self._connect_neo4j()
        except Exception as exc:  # noqa: BLE001
            log.warning("Neo4j unavailable (%s); using in-memory seed graph", exc)

    def _rebuild_adj(self) -> None:
        self._weight_adj: dict[str, list[tuple[str, float]]] = {i: [] for i in self.locations}
        self._baseline_adj: dict[str, list[tuple[str, float]]] = {i: [] for i in self.locations}
        self._sim_adj: dict[str, list[tuple[str, float, float]]] = {i: [] for i in self.locations}
        self._route_lookup: dict[tuple[str, str], dict[str, Any]] = {}
        for r in self.routes:
            s, t = r["source_id"], r["target_id"]
            w = float(r["gds_weight"])
            risk = float(r["predicted_risk"])
            self._weight_adj[s].append((t, w))
            self._weight_adj[t].append((s, w))
            bw = float(r.get("baseline_weight", baseline_weight(r["cost_usd"], r["transit_hours"])))
            self._baseline_adj[s].append((t, bw))
            self._baseline_adj[t].append((s, bw))
            cs = float(self.locations[s]["congestion_index"])
            ct = float(self.locations[t]["congestion_index"])
            self._sim_adj[s].append((t, risk, ct))
            self._sim_adj[t].append((s, risk, cs))
            self._route_lookup[(s, t)] = r
            self._route_lookup[(t, s)] = r

    def _connect_neo4j(self) -> None:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=1.5,
        )
        driver.verify_connectivity()
        with driver.session() as session:
            rec = session.run("MATCH (n:Location) RETURN count(n) AS n").single()
            if rec is None or int(rec["n"]) == 0:
                raise RuntimeError("Neo4j has no Location nodes; run graph/seed.py")
            session.run("CALL gds.graph.drop('logistics', false)")
            session.run(
                """
                CALL gds.graph.project('logistics', 'Location', {
                  ROUTE: {orientation: 'UNDIRECTED', properties: ['gds_weight', 'baseline_weight']}
                })
                """
            )
            session.run("CALL gds.betweenness.write('logistics', {writeProperty: 'betweenness'})")
            rows = session.run(
                """
                MATCH (n:Location)
                RETURN n.id AS id, n.name AS name, n.kind AS kind, n.lat AS lat, n.lng AS lng,
                       n.capacity AS capacity, n.avg_delay AS avg_delay,
                       n.congestion_index AS congestion_index, n.region AS region,
                       coalesce(n.predicted_risk, 0.15) AS predicted_risk,
                       coalesce(n.betweenness, 0.0) AS betweenness
                """
            )
            self.locations = {}
            mx = 0.0
            for row in rows:
                d = dict(row)
                mx = max(mx, float(d["betweenness"]))
                self.locations[d["id"]] = d
            mx = mx or 1.0
            for d in self.locations.values():
                d["betweenness_norm"] = float(d["betweenness"]) / mx
            self.routes = []
            for row in session.run(
                """
                MATCH (s:Location)-[r:ROUTE]->(t:Location)
                RETURN s.id AS source_id, t.id AS target_id, r.carrier_id AS carrier_id,
                       r.distance_km AS distance_km, r.cost_usd AS cost_usd,
                       r.historical_delay_hours AS historical_delay_hours,
                       r.predicted_risk AS predicted_risk, r.transit_hours AS transit_hours,
                       r.gds_weight AS gds_weight, r.baseline_weight AS baseline_weight
                """
            ):
                self.routes.append(dict(row))
            self._rebuild_adj()
        self._driver = driver
        self.using_neo4j = True
        self.centrality_backend = "neo4j_gds"

    def names(self) -> dict[str, str]:
        return {i: loc["name"] for i, loc in self.locations.items()}

    def sim_adjacency(self) -> dict[str, list[tuple[str, float, float]]]:
        return self._sim_adj

    def update_node_risk(self, node_id: str, risk: float) -> None:
        self.bulk_update_risks({node_id: risk})

    def bulk_update_risks(self, mapping: dict[str, float]) -> None:
        for node_id, risk in mapping.items():
            if node_id in self.locations:
                self.locations[node_id]["predicted_risk"] = float(risk)
        if self.using_neo4j and self._driver is not None and mapping:
            with self._driver.session() as session:
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (n:Location {id: row.id})
                    SET n.predicted_risk = row.risk
                    """,
                    rows=[{"id": k, "risk": float(v)} for k, v in mapping.items()],
                )

    def update_route_risks_from_nodes(self) -> None:
        for r in self.routes:
            s = self.locations[r["source_id"]]["predicted_risk"]
            t = self.locations[r["target_id"]]["predicted_risk"]
            blended = min(0.95, 0.5 * float(s) + 0.5 * float(t))
            r["predicted_risk"] = blended
            r["gds_weight"] = gds_weight(float(r["cost_usd"]), float(r["transit_hours"]), blended)
        if self.using_neo4j and self._driver is not None:
            with self._driver.session() as session:
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (s:Location {id: row.source_id})-[r:ROUTE]->(t:Location {id: row.target_id})
                    SET r.predicted_risk = row.predicted_risk, r.gds_weight = row.gds_weight
                    """,
                    rows=[{k: r[k] for k in ("source_id", "target_id", "predicted_risk", "gds_weight")} for r in self.routes],
                )
        self._rebuild_adj()

    def _refresh_gds_projection(self) -> None:
        if self._driver is None:
            return
        with self._driver.session() as session:
            session.run("CALL gds.graph.drop('logistics', false)")
            session.run(
                """
                CALL gds.graph.project('logistics', 'Location', {
                  ROUTE: {orientation: 'UNDIRECTED', properties: ['gds_weight', 'baseline_weight']}
                })
                """
            )

    def shortest_path(self, source: str, target: str, weight_property: str = "gds_weight") -> tuple[list[str], float]:
        adj = self._baseline_adj if weight_property == "baseline_weight" else self._weight_adj
        if self.using_neo4j and self._driver is not None:
            try:
                self._refresh_gds_projection()
                with self._driver.session() as session:
                    rec = session.run(
                        f"""
                        MATCH (s:Location {{id: $sid}}), (t:Location {{id: $tid}})
                        CALL gds.shortestPath.dijkstra.stream('logistics', {{
                          sourceNode: s,
                          targetNode: t,
                          relationshipWeightProperty: '{weight_property}'
                        }})
                        YIELD nodeIds, totalCost
                        RETURN [nodeId IN nodeIds | gds.util.asNode(nodeId).id] AS ids, totalCost
                        """,
                        sid=source,
                        tid=target,
                    ).single()
                    if rec is not None:
                        self.last_path_backend = "neo4j_gds"
                        return list(rec["ids"]), float(rec["totalCost"])
            except Exception as exc:  # noqa: BLE001
                log.warning("GDS Dijkstra failed (%s); using local", exc)
        self.last_path_backend = "local"
        return weighted_dijkstra(adj, source, target)

    def path_score(self, node_ids: list[str], unweighted: bool = False) -> dict[str, Any]:
        cost = 0.0
        hours = 0.0
        risks: list[float] = []
        weight = 0.0
        for a, b in zip(node_ids, node_ids[1:]):
            if unweighted:
                dist = 0.0
                # geographic fallback
                sa, sb = self.locations[a], self.locations[b]
                from network import haversine_km

                dist = haversine_km(sa["lat"], sa["lng"], sb["lat"], sb["lng"])
                cost += dist * 0.55
                hours += dist / 35.0
                risks.append(0.5 * float(sa["predicted_risk"]) + 0.5 * float(sb["predicted_risk"]))
                continue
            r = self._route_lookup.get((a, b))
            if r is None:
                sa, sb = self.locations[a], self.locations[b]
                from network import haversine_km

                dist = haversine_km(sa["lat"], sa["lng"], sb["lat"], sb["lng"])
                cost += dist * 0.55
                hours += dist / 35.0
                risks.append(0.5 * float(sa["predicted_risk"]) + 0.5 * float(sb["predicted_risk"]))
            else:
                cost += float(r["cost_usd"])
                hours += float(r["transit_hours"])
                risks.append(float(r["predicted_risk"]))
                weight += float(r["gds_weight"])
        risk = sum(risks)
        legs = [
            {
                "node_id": nid,
                "name": self.locations[nid]["name"],
                "lat": self.locations[nid]["lat"],
                "lng": self.locations[nid]["lng"],
            }
            for nid in node_ids
        ]
        return {
            "node_ids": node_ids,
            "legs": legs,
            "cost_usd": round(cost, 2),
            "time_hours": round(hours, 2),
            "risk": round(risk, 4),
            "gds_weight": round(weight, 5),
        }

    def original_and_alternative(self, source: str, target: str) -> tuple[dict[str, Any], dict[str, Any]]:
        original_ids, _ = self.shortest_path(source, target, "baseline_weight")
        original_backend = self.last_path_backend
        alt_ids, _ = self.shortest_path(source, target, "gds_weight")
        if not alt_ids:
            raise KeyError("no path")
        alternative = self.path_score(alt_ids)
        original = self.path_score(original_ids)
        original["gds_weight"] = round(sum(float(self._route_lookup[(a, b)].get("baseline_weight", 0.0)) for a, b in zip(original_ids, original_ids[1:])), 5)
        self.last_path_backend = "neo4j_gds" if original_backend == "neo4j_gds" and self.last_path_backend == "neo4j_gds" else "local"
        return original, alternative

    def geojson(self) -> dict[str, Any]:
        features: list[dict[str, Any]] = []
        for loc in self.locations.values():
            risk = float(loc.get("predicted_risk", 0.15))
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [loc["lng"], loc["lat"]]},
                    "properties": {
                        "id": loc["id"],
                        "name": loc["name"],
                        "kind": loc["kind"],
                        "capacity": loc["capacity"],
                        "avg_delay": loc["avg_delay"],
                        "congestion_index": loc["congestion_index"],
                        "predicted_risk": risk,
                        "betweenness": loc.get("betweenness", 0.0),
                        "betweenness_norm": loc.get("betweenness_norm", 0.0),
                        "critical": float(loc.get("betweenness_norm", 0.0)) >= 0.55,
                        "region": loc.get("region"),
                    },
                }
            )
        for r in self.routes:
            s, t = self.locations[r["source_id"]], self.locations[r["target_id"]]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[s["lng"], s["lat"]], [t["lng"], t["lat"]]],
                    },
                    "properties": {
                        "source_id": r["source_id"],
                        "target_id": r["target_id"],
                        "predicted_risk": r["predicted_risk"],
                        "cost_usd": r["cost_usd"],
                        "distance_km": r["distance_km"],
                        "carrier_id": r["carrier_id"],
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}


store = GraphStore()
