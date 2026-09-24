import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import mapboxgl, { Map as MapboxMap } from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
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

function usd(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function emptyFc(): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features: [] };
}

export default function App() {
  const mapRef = useRef<MapboxMap | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const selectedRef = useRef<string | null>(null);
  const manualScrubRef = useRef(false);
  const timestampsRef = useRef<string[]>([]);
  const [graph, setGraph] = useState<GeoJSON.FeatureCollection>(emptyFc());
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
    void loadGraph().then(() => setStatus("live"));
  }, [loadGraph]);

  useEffect(() => {
    if (tokenMissing || !containerRef.current || mapRef.current) return;
    mapboxgl.accessToken = TOKEN;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: "mapbox://styles/mapbox/dark-v11",
      center: [54, 22],
      zoom: 1.55,
      projection: "globe",
    });
    mapRef.current = map;
    map.on("load", () => {
      map.addSource("nodes", { type: "geojson", data: emptyFc() });
      map.addSource("edges", { type: "geojson", data: emptyFc() });
      map.addSource("orig-route", { type: "geojson", data: emptyFc() });
      map.addSource("alt-route", { type: "geojson", data: emptyFc() });
      map.addLayer({
        id: "risk-heat",
        type: "heatmap",
        source: "nodes",
        maxzoom: 6,
        paint: {
          "heatmap-weight": ["get", "predicted_risk"],
          "heatmap-intensity": 1.1,
          "heatmap-radius": 32,
          "heatmap-color": [
            "interpolate",
            ["linear"],
            ["heatmap-density"],
            0, "rgba(0,0,0,0)",
            0.2, "#12355b",
            0.45, "#3de0c5",
            0.7, "#ffb020",
            1, "#ff4d6d",
          ],
        },
      });
      map.addLayer({
        id: "edges",
        type: "line",
        source: "edges",
        paint: {
          "line-color": [
            "interpolate", ["linear"], ["get", "predicted_risk"],
            0.05, "#1f3b63",
            0.35, "#6ea8ff",
            0.7, "#ffb020",
            1, "#ff4d6d",
          ],
          "line-width": 1.1,
          "line-opacity": 0.45,
        },
      });
      map.addLayer({
        id: "nodes",
        type: "circle",
        source: "nodes",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "predicted_risk"], 0, 3.2, 1, 9],
          "circle-color": [
            "interpolate", ["linear"], ["get", "predicted_risk"],
            0.1, "#3de0c5",
            0.45, "#ffb020",
            0.8, "#ff4d6d",
          ],
          "circle-stroke-width": 1,
          "circle-stroke-color": "#071018",
        },
      });
      map.addLayer({
        id: "critical",
        type: "circle",
        source: "nodes",
        filter: ["==", ["get", "critical"], true],
        layout: { visibility: "none" },
        paint: {
          "circle-radius": 11,
          "circle-color": "transparent",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#3de0c5",
        },
      });
      map.addLayer({
        id: "cascade",
        type: "circle",
        source: "nodes",
        filter: ["in", "id", ""],
        paint: {
          "circle-radius": 13,
          "circle-color": "#ff4d6d",
          "circle-opacity": 0.25,
          "circle-stroke-color": "#ff4d6d",
          "circle-stroke-width": 2,
        },
      });
      map.addLayer({
        id: "orig-route",
        type: "line",
        source: "orig-route",
        paint: { "line-color": "#ff8fa3", "line-width": 3.5, "line-dasharray": [1.4, 1.2] },
      });
      map.addLayer({
        id: "alt-route",
        type: "line",
        source: "alt-route",
        paint: { "line-color": "#3de0c5", "line-width": 3.5 },
      });
      map.on("click", "nodes", (e) => {
        const id = e.features?.[0]?.properties?.id as string | undefined;
        if (id) void onNode(id);
      });
      map.getCanvas().style.cursor = "pointer";
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [tokenMissing]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("nodes")) return;
    const nodes = graph.features.filter((f) => f.geometry.type === "Point");
    const edges = graph.features.filter((f) => f.geometry.type === "LineString");
    (map.getSource("nodes") as mapboxgl.GeoJSONSource).setData({ type: "FeatureCollection", features: nodes });
    (map.getSource("edges") as mapboxgl.GeoJSONSource).setData({ type: "FeatureCollection", features: edges });
  }, [graph]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getLayer("critical")) return;
    map.setLayoutProperty("critical", "visibility", showCritical ? "visible" : "none");
  }, [showCritical]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getLayer("cascade")) return;
    const ids = ["in", "id", ...Array.from(highlight)];
    map.setFilter("cascade", highlight.size ? ids : ["in", "id", ""]);
  }, [highlight]);

  const lineFrom = (legs: { lng: number; lat: number }[]): GeoJSON.Feature => ({
    type: "Feature",
    properties: {},
    geometry: { type: "LineString", coordinates: legs.map((l) => [l.lng, l.lat]) },
  });

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("orig-route")) return;
    if (!showReroute || !route) {
      (map.getSource("orig-route") as mapboxgl.GeoJSONSource).setData(emptyFc());
      (map.getSource("alt-route") as mapboxgl.GeoJSONSource).setData(emptyFc());
      return;
    }
    (map.getSource("orig-route") as mapboxgl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: [lineFrom(route.original.legs)],
    });
    (map.getSource("alt-route") as mapboxgl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: [lineFrom(route.alternative.legs)],
    });
  }, [route, showReroute]);

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
  }, [loadGraph]);

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

  return (
    <>
      <div ref={containerRef} className="map" />
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
          min={0}
          max={Math.max(0, timestamps.length - 1)}
          value={cursor}
          onChange={(e) => void onScrub(Number(e.target.value))}
        />
      </div>
    </>
  );
}
