# ChainSight

Digital twin prototype for a global logistics network: delay prediction, cascading-failure simulation, and risk-aware reroutes. The ports, routes, carriers and 90-day telemetry are generated synthetic data; no live logistics feed is connected.

## One-command startup

```bash
cp .env.example .env          # paste your Mapbox public token into VITE_MAPBOX_TOKEN
docker compose up --build
```

Then open [http://localhost:5173](http://localhost:5173).

Add a [Mapbox public access token](https://account.mapbox.com/access-tokens/) as `VITE_MAPBOX_TOKEN` in `.env` to use the Mapbox basemap; the example file supplies local defaults for the other settings. If Mapbox, WebGL, or its assets are unavailable, the UI switches to an interactive SVG network view. Neo4j (with Graph Data Science), the API, and map UI come up together. Startup seeds Neo4j and scores synthetic telemetry. The checked-in model is used by default; set `TRAIN_MODEL=1` to explicitly retrain it. A missing model is trained automatically.

## Demo script (after the stack is up)

1. Open the map (dark globe, risk heatmap).
2. Click **Demo: Shanghai cascade** (or click the Shanghai hub).
3. Watch waves propagate; the sidebar shows SHAP drivers, dollars at risk, and SLA breaches.
4. Drag the **time travel** slider.
5. Click **Reroute to Rotterdam** for original vs GDS-weighted alternative.
6. Toggle **GDS critical nodes** (betweenness centrality).

Programmatic check:

```bash
python scripts/demo.py
```

For the timed, three-minute judge walkthrough, target any running API with `python scripts/demo.py --walkthrough --base-url http://localhost:8000`. See [DEMO.md](DEMO.md) for the pitch, click sequence, and code-based answers to likely questions. `python scripts/parity.py` compares Neo4j/GDS results with the local algorithms when Neo4j is reachable; it was not run in this environment.

To run the same endpoint checks without a listening API (for example in an isolated environment), use the in-process ASGI transport:

```bash
PYTHONPATH=backend DEMO_IN_PROCESS=1 python scripts/demo.py
```

## Local (no Docker)

Python **3.11** is what the backend image uses. A newer local interpreter can work if wheels exist.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=backend python backend/scripts/train.py
PYTHONPATH=backend pytest backend/tests graph/test_network.py graph/test_gds_local.py
PYTHONPATH=backend uvicorn app.main:app --app-dir backend --reload
```

Frontend:

```bash
cd frontend && npm install && npm run dev
```

If Neo4j is not running, the API loads the same synthetic network in memory and uses local betweenness + weighted Dijkstra. HTTP responses identify graph, centrality, and routing backends in `X-Graph-Backend`, `X-Centrality-Backend`, and (for `/reroute`) `X-Path-Backend`; the WebSocket metadata frame also identifies its backends. `graph/seed.py` and backend startup run GDS betweenness, and `/reroute` runs GDS Dijkstra for both cost/time-only baseline and risk-weighted alternative when Neo4j is connected.

The API exposes `GET /ready`; it returns ready only after model loading, graph initialization, GDS projection setup when Neo4j is connected, the warm-up prediction/simulation/reroute, and tick-cache priming. The UI waits for this endpoint before fetching the graph or opening its stream. Compose uses the endpoint for the backend health check.

## Layout

- `graph/` — seed, Cypher, GDS project, synthetic ~40 ports / 30 warehouses / 15 carriers / few hundred routes
- `backend/` — FastAPI, shared feature module, XGBoost+SHAP, cascade + impact, WebSocket replay
- `frontend/` — React + Mapbox GL JS control room
- `scripts/demo.py` — hits `/predict`, `/simulate`, `/impact`, `/reroute`, `/graph`

## API

| Method | Path | Role |
| --- | --- | --- |
| POST | `/predict` | delay probability + top-3 SHAP drivers |
| POST | `/simulate` | hop-decaying risk-weighted cascade waves |
| POST | `/reroute` | cost/time-only shortest path vs risk-weighted shortest path, cumulative risk, and identical-route flag |
| GET | `/impact` | dollars at risk + SLA breaches (`units × delay_days × penalty × p`), optionally at `?at=` |
| GET | `/graph` | GeoJSON (+ optional `?at=` scored SQLite timestamp for scrubbing) |
| GET | `/ready` | readiness after startup warm-up |
| WS | `/ws/stream?speed=50` | replay scored telemetry |

Supporting libraries used to run the named stack: `neo4j` driver, `uvicorn`, `numpy`, `httpx`/`pytest`. SHAP also pulls `scikit-learn`.
