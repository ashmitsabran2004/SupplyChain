import type { Reroute } from "./api";

type Props = {
  graph: GeoJSON.FeatureCollection;
  onNode: (id: string) => void;
  showCritical: boolean;
  highlight: Set<string>;
  showReroute: boolean;
  route: Reroute | null;
  failureMessage: string;
};

const WIDTH = 1200;
const HEIGHT = 600;
const project = (lng: number, lat: number) => ({ x: ((lng + 180) / 360) * WIDTH, y: ((90 - lat) / 180) * HEIGHT });
const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function colorAt(risk: number, stops: [number, string][]): string {
  const value = Math.min(1, Math.max(0, risk));
  if (value <= stops[0][0]) return stops[0][1];
  if (value >= stops[stops.length - 1][0]) return stops[stops.length - 1][1];
  let upper = stops.findIndex(([threshold]) => threshold >= value);
  if (upper < 0) upper = stops.length - 1;
  const lower = Math.max(0, upper - 1);
  const [a, colorA] = stops[lower];
  const [b, colorB] = stops[upper];
  const parse = (hex: string) => hex.match(/[a-f\d]{2}/gi)?.map((part) => Number.parseInt(part, 16)) ?? [0, 0, 0];
  const ca = parse(colorA);
  const cb = parse(colorB);
  const t = b === a ? 0 : (value - a) / (b - a);
  return `#${ca.map((channel, index) => Math.round(channel + (cb[index] - channel) * t).toString(16).padStart(2, "0")).join("")}`;
}

const nodeColor = (risk: number) => colorAt(risk, [[0.1, "#3de0c5"], [0.45, "#ffb020"], [0.8, "#ff4d6d"]]);
const edgeColor = (risk: number) => colorAt(risk, [[0.05, "#1f3b63"], [0.35, "#6ea8ff"], [0.7, "#ffb020"], [1, "#ff4d6d"]]);

function pathForLegs(legs: { lng: number; lat: number }[]): string {
  return legs.map((leg, index) => {
    const point = project(leg.lng, leg.lat);
    return `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`;
  }).join(" ");
}

export default function SvgNetworkMap({ graph = EMPTY, onNode, showCritical, highlight, showReroute, route, failureMessage }: Props) {
  const points = graph.features.filter((feature) => feature.geometry.type === "Point") as GeoJSON.Feature<GeoJSON.Point>[];
  const edges = graph.features.filter((feature) => feature.geometry.type === "LineString") as GeoJSON.Feature<GeoJSON.LineString>[];
  const originalPath = showReroute && route ? pathForLegs(route.original.legs) : "";
  const alternativePath = showReroute && route ? pathForLegs(route.alternative.legs) : "";

  return (
    <div className="svg-map-wrap" aria-label="Offline logistics network map">
      <svg className="svg-network-map" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="xMidYMid slice" role="group" aria-label="Supply chain network in offline map mode">
        <defs>
          <radialGradient id="offline-map-bg"><stop offset="0%" stopColor="#101d2e" /><stop offset="100%" stopColor="#070b12" /></radialGradient>
          <pattern id="offline-map-grid" width="100" height="100" patternUnits="userSpaceOnUse">
            <path d="M 100 0 L 0 0 0 100" fill="none" stroke="#19314b" strokeWidth="1" opacity="0.45" />
          </pattern>
        </defs>
        <rect width={WIDTH} height={HEIGHT} fill="url(#offline-map-bg)" />
        <rect width={WIDTH} height={HEIGHT} fill="url(#offline-map-grid)" />
        {[30, 150, 270, 390, 510].map((y) => <path key={`lat-${y}`} d={`M0 ${y} H${WIDTH}`} stroke="#34516a" strokeWidth="1" opacity="0.26" />)}
        {[200, 400, 600, 800, 1000].map((x) => <path key={`lng-${x}`} d={`M${x} 0 V${HEIGHT}`} stroke="#34516a" strokeWidth="1" opacity="0.26" />)}

        <g className="svg-network-edges" aria-hidden="true">
          {edges.map((edge, index) => {
            const coords = edge.geometry.coordinates;
            if (coords.length < 2) return null;
            const a = project(coords[0][0], coords[0][1]);
            const b = project(coords[coords.length - 1][0], coords[coords.length - 1][1]);
            const risk = Number(edge.properties?.predicted_risk ?? 0.15);
            return <line key={`edge-${index}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={edgeColor(risk)} strokeOpacity="0.42" strokeWidth="1.15" vectorEffect="non-scaling-stroke" />;
          })}
        </g>

        {showReroute && route && <g className="svg-route-overlay" aria-hidden="true">
          <path d={originalPath} fill="none" stroke="#ff8fa3" strokeWidth="4" strokeDasharray="9 7" vectorEffect="non-scaling-stroke" />
          <path d={alternativePath} fill="none" stroke="#3de0c5" strokeWidth="4" vectorEffect="non-scaling-stroke" />
        </g>}

        <g className="svg-network-nodes">
          {points.map((feature) => {
            const [lng, lat] = feature.geometry.coordinates;
            const p = project(lng, lat);
            const props = feature.properties ?? {};
            const id = String(props.id ?? "");
            const name = String(props.name ?? id);
            const risk = Number(props.predicted_risk ?? 0.15);
            const critical = showCritical && Boolean(props.critical);
            const cascading = highlight.has(id);
            const radius = 3.5 + Math.min(1, Math.max(0, risk)) * 4;
            return <g key={id} className="svg-node" transform={`translate(${p.x} ${p.y})`} role="button" tabIndex={0} aria-label={`Select ${name}, risk ${risk.toFixed(2)}`} onClick={() => onNode(id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onNode(id); } }}>
              <title>{`${name} · risk ${risk.toFixed(2)}${critical ? " · critical" : ""}${cascading ? " · cascade affected" : ""}`}</title>
              {cascading && <circle r={radius + 8} fill="#ff4d6d" fillOpacity="0.16" stroke="#ff4d6d" strokeWidth="2" strokeOpacity="0.9" vectorEffect="non-scaling-stroke" />}
              {critical && <circle r={radius + 5} fill="none" stroke="#3de0c5" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
              <circle r={radius} fill={nodeColor(risk)} stroke="#071018" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
            </g>;
          })}
        </g>
      </svg>
      <div className="offline-badge">offline map mode</div>
      <div className="map-error-banner" role="status" aria-live="polite">
        <strong>Mapbox unavailable</strong><span>{failureMessage}</span>
      </div>
    </div>
  );
}
