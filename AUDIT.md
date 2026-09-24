# ChainSight implementation audit

Status reflects the changes in this work session. Docker and live Neo4j/GDS checks remain pending for the user, as requested.

| Area | Status | Findings |
| --- | --- | --- |
| Route comparison honesty | Done | `backend/app/graph_store.py` compares a cost/time-only Dijkstra baseline with a risk-weighted alternative, reports cumulative edge risk, and returns an identical-route flag. The in-process demo passed distinct route/score checks on the local fallback. |
| Neo4j and GDS | Pending user check | Projection setup and GDS route/centrality calls are implemented. `scripts/parity.py` compares both route choices and top 10 critical nodes against local algorithms, prints differences, returns non-zero on mismatch, and reports a skip if Neo4j is unreachable. It was not run. Live Neo4j/GDS behavior and parity are pending the user. |
| Frontend bundle and map fallback | Partial | `MapView` lazy-loads Mapbox GL ESM, catches initialization/import errors, listens to `error` and `style.load`, checks WebGL2 and container size, and falls back to an interactive SVG map with risk colors, critical nodes, cascades, routes, and node selection. A boundary catches a failed MapView chunk. Nginx serves JS/CSS with explicit MIME types and returns 404 for missing assets instead of the SPA shell. The production build succeeds; the two deferred Mapbox chunks still exceed Vite's 500 kB warning threshold (core 775.20 kB; shared 587.02 kB). Docker/nginx runtime verification is pending the user. |
| Backend warm-up/readiness | Partial | Lifespan loads the model, rebuilds graph indexes, initializes the stream/tick cache, runs a throwaway prediction and simulation, then reroutes before `/ready` reports ready. Compose backend health check calls `/ready`; the frontend waits before loading the graph and opening the stream. The local in-process lifespan reached ready. Docker startup/health behavior remains pending user verification. |
| Frontend completeness | Done | `frontend/src/App.tsx` shows `/impact` dollar exposure and SLA count, consumes WebSocket ticks, refreshes selected-node impact/cascade for live ticks, and displays backend-ready status. The Mapbox and SVG renderers share risk, cascade, critical-node, route, click-selection, and historical snapshot state. |
| Time slider correctness | Done | `backend/app/main.py` and `backend/app/tick_store.py` load snapshots from scored SQLite ticks. Scrubbing updates nodes/edges, selected-node impact, and cascade; it clears values unavailable in historical tick records. |
| Cascade simulation | Done | `backend/app/simulate.py` uses hop-decaying, risk/congestion-weighted propagation and ordered waves with probability increase, delay, and arrival step. The UI animates waves and uses the same timestamp when scrubbing. |
| Model pipeline | Done | Training and serving share `backend/app/features.py`; `backend/app/ml_service.py` rejects metadata drift. The entrypoint preserves existing artifacts unless `TRAIN_MODEL=1` is set, and trains if artifacts are absent. |
| Tests | Done | `CHAINSIGHT_DISABLE_NEO4J=1 PYTHONPATH=backend .venv/bin/pytest -q` passed: 19 tests. |
| Demo and clean startup | Partial | `scripts/demo.py` supports a timed 180-second walkthrough and a target `--base-url`; `DEMO.md` documents the pitch, click sequence, formulas, and synthetic-data limits. The in-process demo passed all five checks. First-start Docker Compose, clean-clone startup, and the timed walkthrough against a running API are not verified here. |

## References

- Backend lifecycle/readiness: `backend/app/main.py`, `backend/app/graph_store.py`, `backend/app/stream.py`, `backend/app/tick_store.py`
- Graph generation and GDS seed: `graph/network.py`, `graph/seed.py`, `graph/gds_local.py`
- UI, offline renderer, and asset serving: `frontend/src/App.tsx`, `frontend/src/MapView.tsx`, `frontend/src/MapLoadBoundary.tsx`, `frontend/src/SvgNetworkMap.tsx`, `frontend/nginx.conf`, `frontend/vite.config.ts`
- Model and formulas: `backend/scripts/train.py`, `backend/app/features.py`, `backend/app/ml_service.py`, `backend/app/simulate.py`, `backend/app/impact.py`
- Walkthrough and parity: `scripts/demo.py`, `scripts/parity.py`, `DEMO.md`
- Compose health check and coverage: `docker-compose.yml`, `backend/tests/`
