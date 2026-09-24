"""Synthetic but geographically plausible logistics network."""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Any

# Blend used by GDS Dijkstra: higher weight = less attractive path.
COST_W = 0.30
TIME_W = 0.30
RISK_W = 0.40

RANDOM_SEED = 42


@dataclass(frozen=True)
class LocationSpec:
    id: str
    name: str
    kind: str  # port | warehouse | distribution_center
    lat: float
    lng: float
    capacity: int
    avg_delay: float
    congestion_index: float
    region: str


@dataclass(frozen=True)
class CarrierSpec:
    id: str
    name: str
    reliability: float
    mode: str


@dataclass(frozen=True)
class RouteSpec:
    source_id: str
    target_id: str
    carrier_id: str
    distance_km: float
    cost_usd: float
    historical_delay_hours: float
    predicted_risk: float
    transit_hours: float
    gds_weight: float
    baseline_weight: float


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def gds_weight(cost_usd: float, transit_hours: float, predicted_risk: float) -> float:
    """Normalize roughly onto a 0.1–3.0 scale Neo4j GDS Dijkstra can use."""
    cost_n = min(cost_usd / 80_000.0, 1.5)
    time_n = min(transit_hours / 400.0, 1.5)
    risk_n = max(0.02, min(predicted_risk, 1.0))
    return max(0.05, COST_W * cost_n + TIME_W * time_n + RISK_W * risk_n)


def baseline_weight(cost_usd: float, transit_hours: float) -> float:
    """Comparable normalized cost/time weight, deliberately excluding risk."""
    cost_n = min(cost_usd / 80_000.0, 1.5)
    time_n = min(transit_hours / 400.0, 1.5)
    return max(0.05, 0.5 * cost_n + 0.5 * time_n)


def _ports() -> list[LocationSpec]:
    raw: list[tuple[str, str, float, float, str]] = [
        ("port-shanghai", "Shanghai", 31.2304, 121.4737, "APAC"),
        ("port-singapore", "Singapore", 1.2644, 103.8220, "APAC"),
        ("port-ningbo", "Ningbo-Zhoushan", 29.8683, 121.5440, "APAC"),
        ("port-shenzhen", "Shenzhen Yantian", 22.5833, 114.2667, "APAC"),
        ("port-guangzhou", "Guangzhou Nansha", 22.7667, 113.6000, "APAC"),
        ("port-busan", "Busan", 35.1028, 129.0403, "APAC"),
        ("port-qingdao", "Qingdao", 36.0671, 120.3826, "APAC"),
        ("port-hongkong", "Hong Kong", 22.3080, 114.1716, "APAC"),
        ("port-tianjin", "Tianjin", 38.9756, 117.7469, "APAC"),
        ("port-xiamen", "Xiamen", 24.4798, 118.0894, "APAC"),
        ("port-kaohsiung", "Kaohsiung", 22.6273, 120.3014, "APAC"),
        ("port-tokyo", "Tokyo-Yokohama", 35.4437, 139.6380, "APAC"),
        ("port-nagoya", "Nagoya", 35.0900, 136.8800, "APAC"),
        ("port-kobe", "Osaka-Kobe", 34.6901, 135.1955, "APAC"),
        ("port-laem", "Laem Chabang", 13.0827, 100.8830, "APAC"),
        ("port-tanjung-pelepas", "Tanjung Pelepas", 1.3626, 103.5512, "APAC"),
        ("port-klang", "Port Klang", 3.0000, 101.4000, "APAC"),
        ("port-priok", "Tanjung Priok", -6.1045, 106.8865, "APAC"),
        ("port-hcmc", "Ho Chi Minh Cat Lai", 10.7600, 106.7800, "APAC"),
        ("port-colombo", "Colombo", 6.9410, 79.8428, "APAC"),
        ("port-rotterdam", "Rotterdam", 51.9225, 4.4792, "EMEA"),
        ("port-antwerp", "Antwerp", 51.2993, 4.2922, "EMEA"),
        ("port-hamburg", "Hamburg", 53.5461, 9.9661, "EMEA"),
        ("port-bremerhaven", "Bremerhaven", 53.5396, 8.5809, "EMEA"),
        ("port-felixstowe", "Felixstowe", 51.9542, 1.3512, "EMEA"),
        ("port-lehavre", "Le Havre", 49.4900, 0.1000, "EMEA"),
        ("port-valencia", "Valencia", 39.4450, -0.3167, "EMEA"),
        ("port-algeciras", "Algeciras", 36.1333, -5.4500, "EMEA"),
        ("port-piraeus", "Piraeus", 37.9475, 23.6247, "EMEA"),
        ("port-jebelali", "Jebel Ali", 24.9857, 55.0700, "EMEA"),
        ("port-durban", "Durban", -29.8683, 31.0250, "EMEA"),
        ("port-la", "Los Angeles", 33.7405, -118.2710, "AMER"),
        ("port-longbeach", "Long Beach", 33.7542, -118.2165, "AMER"),
        ("port-ny", "New York-New Jersey", 40.6681, -74.0451, "AMER"),
        ("port-savannah", "Savannah", 32.0809, -81.0912, "AMER"),
        ("port-houston", "Houston", 29.7280, -95.2660, "AMER"),
        ("port-vancouver", "Vancouver", 49.2890, -123.1110, "AMER"),
        ("port-santos", "Santos", -23.9618, -46.3322, "AMER"),
        ("port-melbourne", "Melbourne", -37.8410, 144.9090, "APAC"),
        ("port-sydney", "Sydney", -33.8590, 151.2090, "APAC"),
    ]
    rng = random.Random(RANDOM_SEED)
    ports: list[LocationSpec] = []
    for i, (lid, name, lat, lng, region) in enumerate(raw):
        hub = lid in {"port-shanghai", "port-singapore", "port-rotterdam", "port-la", "port-jebelali"}
        ports.append(
            LocationSpec(
                id=lid,
                name=name,
                kind="port",
                lat=lat,
                lng=lng,
                capacity=rng.randint(180_000, 480_000) + (220_000 if hub else 0),
                avg_delay=round(rng.uniform(4.0, 28.0) + (8.0 if hub else 0.0), 2),
                congestion_index=round(rng.uniform(0.18, 0.72) + (0.18 if hub else 0.0), 3),
                region=region,
            )
        )
    return ports


def _inland(ports: list[LocationSpec], kind: str, count: int, prefix: str, seed: int) -> list[LocationSpec]:
    rng = random.Random(seed)
    names_wh = [
        "Inland DC",
        "Bonded Warehouse",
        "Cross-dock",
        "Rail Head",
        "Free Trade Zone",
        "Cold Chain Hub",
        "E-com Fulfillment",
        "Spare Parts Depot",
    ]
    out: list[LocationSpec] = []
    for i in range(count):
        parent = ports[i % len(ports)]
        # Offset 40–180 km inland (approx degrees)
        dlat = rng.uniform(0.35, 1.6) * rng.choice([-1, 1])
        dlng = rng.uniform(0.35, 1.8) * rng.choice([-1, 1])
        lat = max(-55.0, min(62.0, parent.lat + dlat))
        lng = parent.lng + dlng
        if lng > 180:
            lng -= 360
        if lng < -180:
            lng += 360
        out.append(
            LocationSpec(
                id=f"{prefix}-{i+1:02d}",
                name=f"{parent.name} {rng.choice(names_wh)} {i+1}",
                kind=kind,
                lat=round(lat, 4),
                lng=round(lng, 4),
                capacity=rng.randint(25_000, 140_000),
                avg_delay=round(rng.uniform(2.0, 16.0), 2),
                congestion_index=round(rng.uniform(0.08, 0.55), 3),
                region=parent.region,
            )
        )
    return out


def _carriers() -> list[CarrierSpec]:
    names = [
        ("car-msc", "MSC", "ocean"),
        ("car-maersk", "Maersk", "ocean"),
        ("car-cma", "CMA CGM", "ocean"),
        ("car-cosco", "COSCO", "ocean"),
        ("car-hapag", "Hapag-Lloyd", "ocean"),
        ("car-evergreen", "Evergreen", "ocean"),
        ("car-one", "Ocean Network Express", "ocean"),
        ("car-yangming", "Yang Ming", "ocean"),
        ("car-hmm", "HMM", "ocean"),
        ("car-zim", "ZIM", "ocean"),
        ("car-dhl", "DHL Global Forwarding", "air_road"),
        ("car-kuehne", "Kuehne+Nagel", "air_road"),
        ("car-dbschenker", "DB Schenker", "rail_road"),
        ("car-ups", "UPS Supply Chain", "air_road"),
        ("car-fedex", "FedEx Trade Networks", "air_road"),
    ]
    rng = random.Random(RANDOM_SEED + 7)
    return [
        CarrierSpec(id=cid, name=name, reliability=round(rng.uniform(0.78, 0.97), 3), mode=mode)
        for cid, name, mode in names
    ]


def _connect_pair(
    rng: random.Random,
    a: LocationSpec,
    b: LocationSpec,
    carriers: list[CarrierSpec],
    ocean: bool,
) -> RouteSpec:
    dist = haversine_km(a.lat, a.lng, b.lat, b.lng)
    if ocean:
        speed_kmh = rng.uniform(28.0, 42.0)
        cost = dist * rng.uniform(0.35, 0.85) + rng.uniform(800, 4000)
        carrier = rng.choice([c for c in carriers if c.mode == "ocean"])
    else:
        speed_kmh = rng.uniform(45.0, 75.0)
        cost = dist * rng.uniform(0.9, 1.8) + rng.uniform(120, 900)
        inland = [c for c in carriers if c.mode != "ocean"]
        carrier = rng.choice(inland if inland else carriers)
    transit = dist / speed_kmh
    hist_delay = rng.uniform(1.0, 18.0) * (1.15 if a.congestion_index > 0.6 or b.congestion_index > 0.6 else 1.0)
    reliability_pen = 1.0 - carrier.reliability
    predicted = min(
        0.95,
        0.12
        + 0.35 * ((a.congestion_index + b.congestion_index) / 2)
        + 0.25 * reliability_pen
        + 0.15 * min(hist_delay / 24.0, 1.0)
        + rng.uniform(-0.05, 0.08),
    )
    predicted = max(0.03, predicted)
    return RouteSpec(
        source_id=a.id,
        target_id=b.id,
        carrier_id=carrier.id,
        distance_km=round(dist, 1),
        cost_usd=round(cost, 2),
        historical_delay_hours=round(hist_delay, 2),
        predicted_risk=round(predicted, 4),
        transit_hours=round(transit, 2),
        gds_weight=round(gds_weight(cost, transit, predicted), 5),
        baseline_weight=round(baseline_weight(cost, transit), 5),
    )


def build_network() -> dict[str, Any]:
    rng = random.Random(RANDOM_SEED)
    ports = _ports()
    warehouses = _inland(ports, "warehouse", 30, "wh", RANDOM_SEED + 1)
    dcs = _inland(ports, "distribution_center", 12, "dc", RANDOM_SEED + 2)
    locations = ports + warehouses + dcs
    carriers = _carriers()
    by_id = {loc.id: loc for loc in locations}

    routes: list[RouteSpec] = []
    seen: set[tuple[str, str]] = set()

    def add_route(a: LocationSpec, b: LocationSpec, ocean: bool) -> None:
        key = tuple(sorted((a.id, b.id)))
        if a.id == b.id or key in seen:
            return
        seen.add(key)
        routes.append(_connect_pair(rng, a, b, carriers, ocean=ocean))

    apac = [p for p in ports if p.region == "APAC"]
    emea = [p for p in ports if p.region == "EMEA"]
    amer = [p for p in ports if p.region == "AMER"]

    # Dense intra-region ocean links
    for group in (apac, emea, amer):
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if haversine_km(a.lat, a.lng, b.lat, b.lng) < 4200 or rng.random() < 0.35:
                    add_route(a, b, ocean=True)

    # Trunk east-west corridors through mega hubs
    trunks = [
        "port-shanghai",
        "port-singapore",
        "port-rotterdam",
        "port-jebelali",
        "port-la",
        "port-ny",
        "port-busan",
        "port-hamburg",
        "port-colombo",
        "port-santos",
    ]
    trunk_nodes = [by_id[t] for t in trunks if t in by_id]
    for i, a in enumerate(trunk_nodes):
        for b in trunk_nodes[i + 1 :]:
            add_route(a, b, ocean=True)

    # Each non-hub port links to 2 nearest hubs
    hubs = [by_id[h] for h in ["port-shanghai", "port-singapore", "port-rotterdam", "port-la", "port-jebelali"]]
    for p in ports:
        nearest = sorted(hubs, key=lambda h: haversine_km(p.lat, p.lng, h.lat, h.lng))[:2]
        for h in nearest:
            add_route(p, h, ocean=True)

    # Inland spokes: warehouse/DC to nearest 1–2 ports in region
    inland = warehouses + dcs
    for node in inland:
        regional = [p for p in ports if p.region == node.region]
        nearest = sorted(regional, key=lambda p: haversine_km(node.lat, node.lng, p.lat, p.lng))[:2]
        for p in nearest:
            add_route(node, p, ocean=False)
        # a few warehouse-to-DC links
        if node.kind == "warehouse" and rng.random() < 0.45:
            dc = rng.choice(dcs)
            add_route(node, dc, ocean=False)

    # Extra ocean links until we land in a few hundred
    while len(routes) < 280:
        a, b = rng.choice(ports), rng.choice(ports)
        add_route(a, b, ocean=True)

    return {
        "locations": [asdict(x) for x in locations],
        "carriers": [asdict(x) for x in carriers],
        "routes": [asdict(x) for x in routes],
        "meta": {
            "port_count": len(ports),
            "warehouse_count": len(warehouses),
            "dc_count": len(dcs),
            "carrier_count": len(carriers),
            "route_count": len(routes),
        },
    }
