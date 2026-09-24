"""Offline checks for the synthetic network (no Neo4j required)."""

from __future__ import annotations

from network import build_network, gds_weight


def test_network_shape() -> None:
    net = build_network()
    meta = net["meta"]
    assert meta["port_count"] == 40
    assert meta["warehouse_count"] == 30
    assert meta["dc_count"] == 12
    assert meta["carrier_count"] == 15
    assert 250 <= meta["route_count"] <= 450


def test_coordinates_are_real() -> None:
    net = build_network()
    shanghai = next(x for x in net["locations"] if x["id"] == "port-shanghai")
    rotterdam = next(x for x in net["locations"] if x["id"] == "port-rotterdam")
    assert abs(shanghai["lat"] - 31.2304) < 1e-6
    assert abs(rotterdam["lng"] - 4.4792) < 1e-6
    for loc in net["locations"]:
        assert -90 <= loc["lat"] <= 90
        assert -180 <= loc["lng"] <= 180


def test_route_properties() -> None:
    net = build_network()
    loc_ids = {x["id"] for x in net["locations"]}
    car_ids = {x["id"] for x in net["carriers"]}
    for r in net["routes"]:
        assert r["source_id"] in loc_ids
        assert r["target_id"] in loc_ids
        assert r["carrier_id"] in car_ids
        assert r["distance_km"] > 0
        assert r["cost_usd"] > 0
        assert 0 < r["predicted_risk"] < 1
        expected = gds_weight(r["cost_usd"], r["transit_hours"], r["predicted_risk"])
        assert abs(r["gds_weight"] - expected) < 1e-4


if __name__ == "__main__":
    test_network_shape()
    test_coordinates_are_real()
    test_route_properties()
    print("graph/test_network.py OK")
