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
import MapLoadBoundary from "./MapLoadBoundary";
import SvgNetworkMap from "./SvgNetworkMap";

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
  const presenterRun = useRef(0);
  const [graph, setGraph] = useState<GeoJSON.FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [timestamps, setTimestamps] = useState<string[]>([]);
  const [cursor, setCursor] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [drivers, setDrivers] = useState<ShapDriver[]>([]);
  const [exp, setExp] = useState<Impact | null>(null);
  const [impactScenario, setImpactScenario] = useState("Normal snapshot");
  const [sim, setSim] = useState<Simulation | null>(null);
  const [highlight, setHighlight] = useState<Set<string>>(new Set());
  const [waveNodes, setWaveNodes] = useState<Set<string>>(new Set());
  const [waveLabel, setWaveLabel] = useState("");
  const [cascadeExposure, setCascadeExposure] = useState(0);
  const [showCritical, setShowCritical] = useState(false);
  const [showReroute, setShowReroute] = useState(false);
  const [route, setRoute] = useState<Reroute | null>(null);
  const [status, setStatus] = useState("loading network");
  const [apiReady, setApiReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [playSpeed, setPlaySpeed] = useState(1);
  const [wsLive, setWsLive] = useState(false);
  const [severity, setSeverity] = useState(0.72);
  const [failedNodes, setFailedNodes] = useState<string[]>([]);
  const [addingFailure, setAddingFailure] = useState(false);
  const [showHeat, setShowHeat] = useState(true);
  const [showEdges, setShowEdges] = useState(true);
  const [showNodes, setShowNodes] = useState(true);
  const [searchText, setSearchText] = useState("");
  const [searchTarget, setSearchTarget] = useState<string | null>(null);
  const [routeSource, setRouteSource] = useState(HUB_DEFAULT);
  const [routeTarget, setRouteTarget] = useState(REROUTE_TARGET);
  useEffect(() => { selectedRef.current = selected; }, [selected]);

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
    const seen = new Set<string>();
    setCascadeExposure(0);
    for (let i = 0; i < result.waves.length; i += 1) {
      const ids = new Set<string>();
      result.waves.slice(0, i + 1).forEach((w) => w.forEach((n) => ids.add(n.node_id)));
      const currentWave = result.waves[i].filter((n) => !seen.has(n.node_id));
      currentWave.forEach((n) => seen.add(n.node_id));
      setHighlight(ids);
      setWaveNodes(new Set(currentWave.map((n) => n.node_id)));
      setWaveLabel(`Step ${i + 1}/${result.waves.length} · wave ${i + 1} · ${result.waves[i].length} nodes`);
      const impacts = await Promise.all(currentWave.map((node) => impact(node.node_id).catch(() => null)));
      setCascadeExposure((total) => total + impacts.reduce((sum, item) => sum + (item?.dollars_at_risk ?? 0), 0));
      await new Promise((r) => setTimeout(r, 700));
    }
  }, []);

  const onNode = useCallback(
    async (nodeId: string) => {
      manualScrubRef.current = false;
      const roots = addingFailure && failedNodes.length ? [...new Set([...failedNodes, nodeId])] : [nodeId];
      setFailedNodes(roots);
      setAddingFailure(false);
      setSelected(nodeId);
      setStatus(`scoring ${roots.length} failed node${roots.length === 1 ? "" : "s"}`);
      const results = await Promise.all(roots.map(async (id) => {
        const [pred, simulation, nodeImpact] = await Promise.all([predict(id, severity), simulate(id), impact(id)]);
        return { id, pred, simulation, nodeImpact };
      }));
      const merged = new Map<number, Map<string, Simulation["waves"][number][number]>>();
      results.forEach(({ simulation }) => simulation.waves.forEach((wave, index) => {
        const bucket = merged.get(index) ?? new Map();
        wave.forEach((node) => {
          const previous = bucket.get(node.node_id);
          if (!previous || node.probability_increase > previous.probability_increase) bucket.set(node.node_id, node);
        });
        merged.set(index, bucket);
      }));
      const simRes: Simulation = { ...results[0].simulation, origin_id: roots.join(" + "), waves: [...merged.entries()].sort(([a], [b]) => a - b).map(([, wave]) => [...wave.values()]) };
      setDrivers(results[0].pred.drivers);
      setSim(simRes);
      setExp({ ...results[0].nodeImpact, dollars_at_risk: results.reduce((sum, result) => sum + result.nodeImpact.dollars_at_risk, 0), sla_breaches: results.reduce((sum, result) => sum + result.nodeImpact.sla_breaches, 0) });
      setImpactScenario(`Disrupted · ${roots.length} node${roots.length === 1 ? "" : "s"}`);
      setStatus("cascade");
      await animateCascade(simRes);
      setStatus("stable");
    },
    [animateCascade, addingFailure, failedNodes, severity],
  );

  const onReroute = async () => {
    setStatus("rerouting");
    const r = await reroute(routeSource, routeTarget);
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
    setImpactScenario("Normal snapshot");
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

  const startPresenter = useCallback(() => {
    const run = ++presenterRun.current;
    const started = Date.now();
    const waitUntil = async (seconds: number) => {
      while (presenterRun.current === run && Date.now() - started < seconds * 1000) {
        await new Promise((resolve) => setTimeout(resolve, Math.min(250, seconds * 1000 - (Date.now() - started))));
      }
      return presenterRun.current === run;
    };
    setPresenterCaption("0:00 · Cascading a Shanghai disruption through the network");
    void onNode(HUB_DEFAULT);
    void (async () => {
      if (!await waitUntil(40)) return;
      setPresenterCaption("0:40 · SHAP explains the top delay drivers; exposure and SLA estimates update in the sidebar");
      if (!await waitUntil(80)) return;
      setPresenterCaption("1:20 · Reviewing a historical snapshot");
      if (timestamps.length) await onScrub(Math.floor(timestamps.length / 2));
      if (!await waitUntil(125)) return;
      setPresenterCaption("2:05 · Comparing cost/time and risk-weighted routes");
      const result = await reroute(HUB_DEFAULT, REROUTE_TARGET);
      if (presenterRun.current !== run) return;
      setRoute(result); setShowReroute(true);
      if (!await waitUntil(180)) return;
      setPresenterCaption("3:00 · Walkthrough complete");
      setPresenterActive(false);
    })();
  }, [onNode, timestamps]);
  const [presenterActive, setPresenterActive] = useState(false);
  const [presenterCaption, setPresenterCaption] = useState("");
  const beginPresenter = () => { setPresenterActive(true); startPresenter(); };
  const stopPresenter = () => { presenterRun.current += 1; setPresenterActive(false); setPresenterCaption("Walkthrough stopped"); };

  useEffect(() => {
    if (!playing || timestamps.length < 2) return;
    const timer = window.setInterval(() => {
      if (cursor >= timestamps.length - 1) { setPlaying(false); return; }
      void onScrub(cursor + 1);
    }, 1000 / playSpeed);
    return () => window.clearInterval(timer);
  }, [playing, playSpeed, cursor, timestamps]);

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
              setImpactScenario("Normal snapshot");
              setHighlight(new Set(simRes.waves.flatMap((w) => w.map((n) => n.node_id))));
              setWaveLabel(`live · ${simRes.waves.length} waves`);
            });
          }
        }
      }
      if (msg.type === "done") setWsLive(false);
    };
    ws.onopen = () => { setWsLive(true); setStatus("live stream connected"); };
    ws.onerror = () => { setWsLive(false); setStatus("stream unavailable"); };
    ws.onclose = () => setWsLive(false);
    return () => { setWsLive(false); ws.close(); };
  }, [loadGraph, apiReady]);

  const selectedName = useMemo(() => {
    const f = graph.features.find((x) => x.properties && x.properties.id === selected);
    return (f?.properties?.name as string | undefined) ?? selected ?? "click a hub";
  }, [graph, selected]);

  if (!apiReady) return <div className="startup-loading"><h1>ChainSight</h1><p role="status" aria-live="polite">{status}…</p></div>;

  return (
    <>
      <MapLoadBoundary fallback={(error) => <SvgNetworkMap graph={graph} onNode={onNode} showCritical={showCritical} highlight={highlight} waveNodes={waveNodes} showReroute={showReroute} route={route} failureMessage={`Map component chunk failed: ${error.message}`} showHeat={showHeat} showEdges={showEdges} showNodes={showNodes} searchTarget={searchTarget} /> }>
        <Suspense fallback={<div className="map-loading">Loading map component…</div>}>
          <MapView token={TOKEN} graph={graph} onNode={onNode} showCritical={showCritical} highlight={highlight} waveNodes={waveNodes} showReroute={showReroute} route={route} showHeat={showHeat} showEdges={showEdges} showNodes={showNodes} searchTarget={searchTarget} />
        </Suspense>
      </MapLoadBoundary>
      <div className="hud topbar">
        <div className="brand">
          <h1>ChainSight</h1>
          <p>supply-chain digital twin · {status}</p>
        </div>
        <div className="toggles">
          <div className="search-control"><input list="port-search-list" value={searchText} placeholder="Search port…" onChange={(event) => setSearchText(event.target.value)} /><datalist id="port-search-list">{graph.features.filter((f) => f.geometry.type === "Point" && ["port", "hub"].includes(String(f.properties?.kind))).map((f) => <option key={String(f.properties?.id)} value={String(f.properties?.name)} />)}</datalist><button onClick={() => { const match = graph.features.find((f) => f.geometry.type === "Point" && (f.properties?.name === searchText || f.properties?.id === searchText)); if (match) setSearchTarget(String(match.properties?.id)); }}>Find</button></div>
          <button className={showCritical ? "on" : ""} onClick={() => setShowCritical((v) => !v)}>
            GDS critical nodes
          </button>
          <label className="map-toggle"><input type="checkbox" checked={showHeat} onChange={(e) => setShowHeat(e.target.checked)} />Heat</label><label className="map-toggle"><input type="checkbox" checked={showEdges} onChange={(e) => setShowEdges(e.target.checked)} />Edges</label><label className="map-toggle"><input type="checkbox" checked={showNodes} onChange={(e) => setShowNodes(e.target.checked)} />Nodes</label>
          <select aria-label="Reroute source port" value={routeSource} onChange={(e) => setRouteSource(e.target.value)}>{graph.features.filter((f) => f.geometry.type === "Point" && ["port", "hub"].includes(String(f.properties?.kind))).map((f) => <option key={String(f.properties?.id)} value={String(f.properties?.id)}>{String(f.properties?.name)}</option>)}</select><select aria-label="Reroute destination port" value={routeTarget} onChange={(e) => setRouteTarget(e.target.value)}>{graph.features.filter((f) => f.geometry.type === "Point" && ["port", "hub"].includes(String(f.properties?.kind))).map((f) => <option key={String(f.properties?.id)} value={String(f.properties?.id)}>{String(f.properties?.name)}</option>)}</select><button className={showReroute ? "on" : ""} onClick={() => void onReroute()}>Compare routes</button>
          <button onClick={() => void onNode(HUB_DEFAULT)}>Demo: Shanghai cascade</button>
          {!presenterActive ? <button onClick={beginPresenter}>Start demo</button> : <button className="on" onClick={stopPresenter}>Stop demo</button>}
        </div>
      </div>
      {presenterCaption && <div className="hud presenter-caption" role="status" aria-live="polite">{presenterCaption}</div>}
      <div className="hud map-legend"><b>Network risk</b><span><i className="legend-low" /> Low</span><span><i className="legend-mid" /> Elevated</span><span><i className="legend-high" /> High</span><span><i className="legend-critical" /> GDS critical</span></div>
      <aside className="hud sidebar">
        <h2>{selectedName}</h2>
        <div className="kpis">
          <div className="kpi">
            <span>$ at risk · {impactScenario}</span>
            <strong>{exp ? usd(exp.dollars_at_risk) : "—"}</strong>
          </div>
          <div className="kpi">
            <span>SLA shipments at risk</span>
            <strong>{exp ? exp.sla_breaches.toLocaleString() : "—"}</strong>
          </div>
        </div>
        <h3>What-if disruption</h3>
        <label className="severity-control">Severity {severity.toFixed(2)}
          <input type="range" min="0" max="1" step="0.01" value={severity} onChange={(event) => setSeverity(Number(event.target.value))} aria-label="Disruption severity" />
        </label>
        <div className="failed-list">Failed nodes: {failedNodes.length ? failedNodes.join(", ") : "select a node"}</div>
        <button className={addingFailure ? "primary" : ""} onClick={() => setAddingFailure((value) => !value)}>{addingFailure ? "Click a second failed node…" : "Add second failed node"}</button>
        <h3>SHAP top-3 delay drivers</h3>
        <p className="shap-caption">Positive values raise delay risk; negative values lower it.</p>
        {drivers.length === 0 && <p style={{ color: "var(--muted)", fontSize: 13 }}>SHAP drivers appear after an on-demand disruption score.</p>}
        {drivers.map((d) => (
          <div className="bar-row" key={d.feature}>
            <span>{d.feature.replaceAll("_", " ")}</span>
            <div className="bar-track">
              <div className={`bar-fill ${d.shap >= 0 ? "raises" : "lowers"}`} style={{ width: `${Math.min(100, Math.abs(d.shap) * 180)}%` }} />
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
            <p className="cascade-ticker">Cumulative exposure: {usd(cascadeExposure)}</p>
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
              <div className="recommendation"><strong>Recommendation</strong><span>The risk-weighted route is {route.tradeoff.delta_cost_usd <= 0 ? `${usd(Math.abs(route.tradeoff.delta_cost_usd))} cheaper` : `${usd(route.tradeoff.delta_cost_usd)} more expensive`}, {route.tradeoff.delta_time_hours <= 0 ? `${Math.abs(route.tradeoff.delta_time_hours).toFixed(1)}h faster` : `${route.tradeoff.delta_time_hours.toFixed(1)}h slower`}, and has {Math.abs(route.tradeoff.delta_risk).toFixed(3)} {route.tradeoff.delta_risk <= 0 ? "lower" : "higher"} cumulative risk.</span></div>
              {route.identical && <div>Both methods chose the same route.</div>}
              <div>Baseline: cost/time only · Alternative: risk-weighted · cumulative risk</div>
            </div>
          </>
        )}
      </aside>
      <div className="hud timeline">
        <div className="meta">
          <span>time travel {wsLive && <b className="live-badge">LIVE</b>}</span>
          <span>{timestamps[cursor] ?? "awaiting scored history"}</span>
        </div>
        <div className="timeline-controls">
          <button onClick={() => setPlaying((value) => !value)} disabled={timestamps.length < 2}>{playing ? "Pause" : "Play"}</button>
          <label>Speed <select value={playSpeed} onChange={(event) => setPlaySpeed(Number(event.target.value))}><option value={1}>1x</option><option value={5}>5x</option><option value={25}>25x</option></select></label>
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
