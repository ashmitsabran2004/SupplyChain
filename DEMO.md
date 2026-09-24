# ChainSight: three-minute judge walkthrough

## Pitch script

**0:00–0:40 — Disrupt Shanghai.** Start with the synthetic port network and select **Demo: Shanghai cascade**. ChainSight scores a severe Shanghai disruption, then shows risk propagation through successive network waves. The map color and wave overlay update as affected locations are reached.

**0:40–1:20 — Explain the score and exposure.** Point to the three largest absolute SHAP contributions for the disruption score, then the selected hub's expected dollar exposure and SLA breach estimate. These are model explanations and scenario estimates over generated data, not observations from a shipping operator.

**1:20–2:05 — Look back in time.** Drag the bottom **time travel** slider to a timestamp. The graph, selected-node impact, and cascade use the scored SQLite snapshot at that timestamp.

**2:05–3:00 — Compare routes.** Select **Reroute to Rotterdam**. The dashed pink route minimizes the normalized cost/time baseline; the solid teal route minimizes the risk-weighted score. Compare their cost, hours, and cumulative route risk. Select **GDS critical nodes** to highlight locations with high betweenness centrality.

For a paced API version of those steps, run:

```bash
python scripts/demo.py --walkthrough --base-url http://localhost:8000
```

It takes 180 seconds, with steps scheduled at 0:00, 0:40, 1:20, and 2:05. Every API call reports the graph, centrality, and, for rerouting, path backend from the response headers. `--base-url` can point to any running ChainSight API.

## Exact click sequence

For the automated presentation, wait for the UI status to become live, then click **Start demo**. Captions run the same three-minute schedule above: Shanghai cascade at 0:00, impact explanation at 0:40, middle historical snapshot at 1:20, and Shanghai-to-Rotterdam route comparison at 2:05. Click **Stop demo** at any time.

To present manually:

1. Wait for the API status to become live. Click **Demo: Shanghai cascade** and watch the wave count, pulse rings, and exposure ticker.
2. Read the **What-if disruption** slider value and top three SHAP drivers. To show a combined failure, click **Add second failed node**, then click another node on the map.
3. Drag **time travel** to another timestamp, or use **Play** and choose 1×, 5×, or 25×. **LIVE** indicates an open WebSocket stream.
4. Choose any source and destination in the route selectors, then click **Compare routes**. The dashed pink route is the cost/time baseline; the teal route is risk-weighted. Read the recommendation sentence.
5. Search a port by name and click **Find**. Use the Heat, Edges, and Nodes toggles, plus **GDS critical nodes**, to focus the map.

## Likely judge questions

### Why XGBoost?

The serving model is a persisted `XGBClassifier` trained on tabular telemetry features. The feature vector combines weather, congestion, reliability, rolling delays, seasonality, disruption, utilization, and historical route delay. A boosted tree classifier is a practical fit for nonlinear interactions in this structured input, and the implementation provides probabilities through `predict_proba` plus per-prediction TreeSHAP explanations. Training uses 120 estimators, depth 5, learning rate 0.08, and a chronological 80/20 row split. The validation data is generated synthetically, so its score is not evidence of real-world predictive performance.

### How does propagation decay across hops?

For each traversed edge, the next probability increase is:

```text
incoming_increase × decay × edge_predicted_risk × (0.35 + 0.65 × neighbor_congestion)
```

The default API decay is `0.62`; the walkthrough's simulation request uses `0.78`. An increase below `0.02` is dropped, propagation stops at the requested hop limit (five by default), and a node keeps its stronger reached value. Thus hop count alone does not determine the reduction: edge risk and congestion also affect transmission.

### How is risk-weighted routing different from cost-only routing?

The baseline uses `max(0.05, 0.5 × min(cost_usd / 80,000, 1.5) + 0.5 × min(transit_hours / 400, 1.5))` per edge. It ignores risk. The alternative uses `max(0.05, 0.30 × min(cost_usd / 80,000, 1.5) + 0.30 × min(transit_hours / 400, 1.5) + 0.40 × clamp(predicted_risk, 0.02, 1.0))`. Both minimize additive edge weights, so the alternative can accept more cost or time to avoid higher predicted risk. The response reports raw cumulative cost, time, and risk for each selected path; it does not claim that the alternative is always cheaper or safer under live operating conditions.

### How is the dollar figure computed?

For a selected node, `compute_impact` clamps probability `p` to `[0, 1]`, estimates delay as `6 × p` days, then calculates:

```text
dollars_at_risk = units × expected_delay_days × per_day_penalty_usd × p
                = 12,000 × (6 × p) × $85 × p
```

The default constants are **12,000 units**, **$85 per unit per delay day**, and **6 expected-delay days at probability 1**. The `p` factor represents probability-weighted expected exposure. For example, at `p = 0.5`, expected delay is 3 days and exposure is `$1,530,000`. Deployments can override the first two defaults with `UNITS_DEFAULT` and `PER_DAY_PENALTY_USD`. The SLA estimate separately compares expected delay with a 2-day threshold and scales the estimated breach fraction by probability.

### What are the limits of the synthetic data?

The network, routes, carrier attributes, and 90-day telemetry are generated by seeded code. Telemetry uses a hand-built latent delay probability with injected multi-day hub disruptions; the classifier learns labels sampled from that synthetic probability. It is useful for exercising the application flow, not for validating a real supply-chain forecast. It omits live carrier feeds, calibrated route-level operating costs, actual shipment volumes, and validation against observed delays. The dollar exposure and SLA counts inherit those assumptions.
