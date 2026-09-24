import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchGraph,
  impact,
  predict,
  reroute,
  simulate,
  streamUrl,
  type Impact,
  type Reroute,
  type ShapDriver,
  type Simulation,
} from "./api";

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || "";
const HUB_DEFAULT = "port-shanghai";
const REROUTE_TARGET = "port-rotterdam";
const MapView = lazy(() => import("./MapView"));

function usd(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

export default function App() {
  const selectedRef = useRef<string | null>(null);
  const manualScrubRef = useRef(false);
  const timestampsRef = useRef<string[]>([]);
  const [graph, setGraph] = useState<GeoJSON.FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [timestamps, setTimestamps] = useState<string[]>([]);
  const [cursor, setCursor] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [drivers, setDrivers] = useState<ShapDriver[]>([]);
  const [exp, setExp] = useState<Impact | null>(null);
  const [sim, setSim] = useState<Simulation | null>(null);
  const [highlight, setHighlight] = useState<Set<string>>(new Set());
  const [waveLabel, setWaveLabel] = useState("");
  const [showCritical, setShowCritical] = useState(false);
  const [showReroute, setShowReroute] = useState(false);
  const [route, setRoute] = useState<Reroute | null>(null);
  const [status, setStatus] = useState("loading network");
  const [apiReady, setApiReady] = useState(false);
  useEffect(() => { selectedRef.current = selected; }, [selected]);

  const tokenMissing = !TOKEN || TOKEN.includes("replace_me");

  const loadGraph = useCallback(async (at?: string) => {
    const data = await fetchGraph(at);
    setGraph(data);
    if (data.timestamps?.length) {
      timestampsRef.current = data.timestamps;
      setTimestamps(data.timestamps);
    }
    return data;
  }, []);

  useEffect(() => {
    let active = true;
    const check = async () => {
      while (active) {
        try {
          const res = await fetch(`${import.meta.env.VITE_API_URL ?? "http://localhost:8000"}/ready`);
          if (res.ok) { await loadGraph(); if (active) { setApiReady(true); setStatus("live"); } return; }
        } catch { /* API may still be starting */ }
        if (active) { setStatus("waiting for API warm-up"); await new Promise((resolve) => setTimeout(resolve, 1500)); }
      }
    };
    void check();
    return () => { active = false; };
  }, [loadGraph]);

  const animateCascade = useCallback(async (result: Simulation) => {
    for (let i = 0; i < result.waves.length; i += 1) {
      const ids = new Set<string>();
      result.waves.slice(0, i + 1).forEach((w) => w.forEach((n) => ids.add(n.node_id)));
      setHighlight(ids);
      setWaveLabel(`wave ${i} · ${result.waves[i].length} nodes`);
      await new Promise((r) => setTimeout(r, 700));
    }
  }, []);

  const onNode = useCallback(
    async (nodeId: string) => {
      manualScrubRef.current = false;
      setSelected(nodeId);
      setStatus(`scoring ${nodeId}`);
      const pred = await predict(nodeId);
      const [simRes, imp] = await Promise.all([simulate(nodeId), impact(nodeId)]);
      setDrivers(pred.drivers);
      setSim(simRes);
      setExp(imp);
      setStatus("cascade");
      await animateCascade(simRes);
      setStatus("stable");
    },
    [animateCascade],
  );

  const onReroute = async () => {
    const src = selected ?? HUB_DEFAULT;
    setStatus("rerouting");
    const r = await reroute(src, REROUTE_TARGET);
    setRoute(r);
    setShowReroute(true);
    setStatus("reroute ready");
  };

  const onScrub = async (idx: number) => {
    manualScrubRef.current = true;
    setCursor(idx);
    const ts = timestamps[idx];
    if (!ts) return;
    setStatus("time travel");
    setDrivers([]);
    setShowReroute(false);
    setRoute(null);
    await loadGraph(ts);
    const nodeId = selectedRef.current;
    if (nodeId) {
      const [imp, simRes] = await Promise.all([impact(nodeId, ts), simulate(nodeId, ts)]);
      setExp(imp);
      setSim(simRes);
      const ids = new Set(simRes.waves.flatMap((w) => w.map((n) => n.node_id)));
      setHighlight(ids);
      setWaveLabel(`snapshot · ${simRes.waves.length} waves`);
    }
    setStatus("historical snapshot");
  };

  useEffect(() => {
    if (!apiReady) return;
    const ws = new WebSocket(streamUrl(50));
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data) as { type: string; timestamp?: string; timestamps?: string[]; backend?: string };
      if (msg.type === "meta" && msg.timestamps) {
        timestampsRef.current = msg.timestamps;
        setTimestamps(msg.timestamps);
      }
      if (msg.type === "tick" && msg.timestamp) {
        if (!timestampsRef.current.includes(msg.timestamp)) {
          timestampsRef.current = [...timestampsRef.current, msg.timestamp];
          setTimestamps(timestampsRef.current);
        }
        if (!manualScrubRef.current) {
          const ts = msg.timestamp;
          setCursor(timestampsRef.current.indexOf(ts));
          void loadGraph(ts);
          setDrivers([]);
          setShowReroute(false);
          setRoute(null);
          const nodeId = selectedRef.current;
          if (nodeId) {
            void Promise.all([impact(nodeId, ts), simulate(nodeId, ts)]).then(([imp, simRes]) => {
              if (manualScrubRef.current) return;
              setExp(imp);
              setSim(simRes);
              setHighlight(new Set(simRes.waves.flatMap((w) => w.map((n) => n.node_id))));
              setWaveLabel(`live · ${simRes.waves.length} waves`);
            });
          }
        }
      }
    };
    ws.onopen = () => setStatus("live stream connected");
    ws.onerror = () => setStatus("stream unavailable");
    return () => ws.close();
  }, [loadGraph, apiReady]);

  const selectedName = useMemo(() => {
    const f = graph.features.find((x) => x.properties && x.properties.id === selected);
    return (f?.properties?.name as string | undefined) ?? selected ?? "click a hub";
  }, [graph, selected]);

  if (tokenMissing) {
    return (
      <div className="brand" style={{ margin: 40 }}>
        <h1>ChainSight</h1>
        <p>Set VITE_MAPBOX_TOKEN in .env (copy .env.example). That is the only required secret.</p>
      </div>
    );
  }

  if (!apiReady) return <div className="startup-loading"><h1>ChainSight</h1><p role="status" aria-live="polite">{status}…</p></div>;

  return (
    <>
      <Suspense fallback={<div className="map-loading">Loading map component…</div>}>
        <MapView token={TOKEN} graph={graph} onNode={onNode} showCritical={showCritical} highlight={highlight} showReroute={showReroute} route={route} />
      </Suspense>
      <div className="hud topbar">
        <div className="brand">
          <h1>ChainSight</h1>
          <p>supply-chain digital twin · {status}</p>
        </div>
        <div className="toggles">
          <button className={showCritical ? "on" : ""} onClick={() => setShowCritical((v) => !v)}>
            GDS critical nodes
          </button>
          <button className={showReroute ? "on" : ""} onClick={() => void onReroute()}>
            Reroute to Rotterdam
          </button>
          <button onClick={() => void onNode(HUB_DEFAULT)}>Demo: Shanghai cascade</button>
        </div>
      </div>
      <aside className="hud sidebar">
        <h2>{selectedName}</h2>
        <div className="kpis">
          <div className="kpi">
            <span>$ at risk</span>
            <strong>{exp ? usd(exp.dollars_at_risk) : "—"}</strong>
          </div>
          <div className="kpi">
            <span>SLA breaches</span>
            <strong>{exp ? exp.sla_breaches.toLocaleString() : "—"}</strong>
          </div>
        </div>
        <h3>SHAP top-3 delay drivers</h3>
        {drivers.length === 0 && <p style={{ color: "var(--muted)", fontSize: 13 }}>SHAP drivers appear after an on-demand disruption score.</p>}
        {drivers.map((d) => (
          <div className="bar-row" key={d.feature}>
            <span>{d.feature.replaceAll("_", " ")}</span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${Math.min(100, Math.abs(d.shap) * 180)}%` }} />
            </div>
            <span>{d.shap.toFixed(2)}</span>
          </div>
        ))}
        {sim && (
          <>
            <h3>Cascade</h3>
            <p style={{ fontSize: 13, color: "var(--muted)" }}>
              {waveLabel || `${sim.waves.length} waves from ${sim.origin_id}`}
            </p>
          </>
        )}
        {showReroute && route && (
          <>
            <h3>Reroute tradeoff</h3>
            <div className="compare">
              <div className="orig">
                Original · ${route.original.cost_usd.toFixed(0)} · {route.original.time_hours.toFixed(0)}h · risk{" "}
                {route.original.risk.toFixed(2)}
              </div>
              <div className="alt">
                Alternative · ${route.alternative.cost_usd.toFixed(0)} · {route.alternative.time_hours.toFixed(0)}h · risk{" "}
                {route.alternative.risk.toFixed(2)}
              </div>
              <div>
                Δ cost {route.tradeoff.delta_cost_usd.toFixed(0)} · Δ time {route.tradeoff.delta_time_hours.toFixed(1)}h · Δ
                risk {route.tradeoff.delta_risk.toFixed(3)}
              </div>
              {route.identical && <div>Both methods chose the same route.</div>}
              <div>Baseline: cost/time only · Alternative: risk-weighted · cumulative risk</div>
            </div>
          </>
        )}
      </aside>
      <div className="hud timeline">
        <div className="meta">
          <span>time travel</span>
          <span>{timestamps[cursor] ?? "awaiting scored history"}</span>
        </div>
        <input
          type="range"
          aria-label="Historical time snapshot"
          min={0}
          max={Math.max(0, timestamps.length - 1)}
          value={cursor}
          onChange={(e) => void onScrub(Number(e.target.value))}
        />
      </div>
    </>
  );
}
