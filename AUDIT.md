# ChainSight implementation audit

Status reflects the implementation after the targeted fixes. “Partial” means code is in place but could not be verified against an unavailable external service.

| Area | Status | Findings |
| --- | --- | --- |
| Route comparison honesty | Done | `backend/app/graph_store.py` compares a cost/time-only Dijkstra baseline with a risk-weighted alternative, reports cumulative edge risk, and returns an identical-route flag. API coverage checks a disruption produces distinct cost, time, and risk scores. |
| Neo4j and GDS | Partial | `graph/seed.py` and `backend/app/graph_store.py` project both route weights, execute GDS betweenness, and run GDS Dijkstra; API responses and WebSocket metadata identify graph, centrality, and path backends. The local fallback uses matching weights. Live Neo4j/GDS execution could not be exercised because Docker/Neo4j is unavailable here. |
| Frontend completeness | Done | `frontend/src/App.tsx` shows `/impact` dollar exposure and SLA count, risk-density heat and node layers, consumes WebSocket ticks to update the map, and refreshes selected-node impact/cascade for live ticks. |
| Time slider correctness | Done | `backend/app/main.py` and `backend/app/tick_store.py` load snapshots from scored SQLite ticks. Scrubbing updates nodes/edges, selected-node impact, and cascade; it clears values unavailable in historical tick records. |
| Cascade simulation | Done | `backend/app/simulate.py` uses hop-decaying, risk/congestion-weighted propagation and ordered waves with probability increase, delay, and arrival step. The UI animates waves and uses the same timestamp when scrubbing. |
| Model pipeline | Done | Training and serving share `backend/app/features.py`; `backend/app/ml_service.py` rejects metadata drift. `backend/docker-entrypoint.sh` preserves existing artifacts unless `TRAIN_MODEL=1` is set, and trains if artifacts are absent. |
| Tests | Done | `backend/tests/` covers prediction, propagation, impact, route scoring, and identical paths. Full pytest run passed: 19 tests. |
| Demo and clean startup | Partial | `scripts/demo.py` forces a high-severity Shanghai event, checks multiple cascade waves, and prints PASS/FAIL results. `.env.example` and README document synthetic data and token setup. Demo passed through in-process ASGI; clean Docker Compose startup remains unverified because Docker is unavailable. |

## References

- Backend routing and graph access: `backend/app/graph_store.py`, `backend/app/main.py`
- Graph generation and GDS seed: `graph/network.py`, `graph/seed.py`, `graph/gds_local.py`
- UI and API client: `frontend/src/App.tsx`, `frontend/src/api.ts`
- Training/startup: `backend/scripts/train.py`, `backend/app/features.py`, `backend/app/ml_service.py`, `backend/docker-entrypoint.sh`
- Coverage and run docs: `backend/tests/`, `scripts/demo.py`, `docker-compose.yml`, `README.md`, `.env.example`
