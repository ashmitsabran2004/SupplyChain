export type ShapDriver = { feature: string; shap: number; value: number };

export type WaveNode = {
  node_id: string;
  name: string;
  probability_increase: number;
  delay_days: number;
  arrival_step: number;
};

export type Simulation = {
  origin_id: string;
  waves: WaveNode[][];
  decay: number;
  max_hops: number;
};

export type Impact = {
  node_id: string | null;
  delay_probability: number;
  expected_delay_days: number;
  units: number;
  per_day_penalty_usd: number;
  dollars_at_risk: number;
  sla_breaches: number;
  sla_threshold_days: number;
};

export type RouteScore = {
  node_ids: string[];
  legs: { node_id: string; name: string; lat: number; lng: number }[];
  cost_usd: number;
  time_hours: number;
  risk: number;
  gds_weight: number;
};

export type Reroute = {
  original: RouteScore;
  alternative: RouteScore;
  tradeoff: { delta_cost_usd: number; delta_time_hours: number; delta_risk: number };
  identical: boolean;
  backend: string;
};

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function fetchGraph(at?: string): Promise<GeoJSON.FeatureCollection & { timestamps?: string[] }> {
  const q = at ? `?at=${encodeURIComponent(at)}` : "";
  const res = await fetch(`${API}/graph${q}`);
  if (!res.ok) throw new Error("graph failed");
  return res.json();
}

export async function predict(nodeId: string): Promise<{ delay_probability: number; drivers: ShapDriver[] }> {
  const res = await fetch(`${API}/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId, disruption_event: 1, weather_severity: 0.72 }),
  });
  if (!res.ok) throw new Error("predict failed");
  return res.json();
}

export async function simulate(nodeId: string, at?: string): Promise<Simulation> {
  const res = await fetch(`${API}/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId, max_hops: 5, at }),
  });
  if (!res.ok) throw new Error("simulate failed");
  return res.json();
}

export async function impact(nodeId: string, at?: string): Promise<Impact> {
  const q = new URLSearchParams({ node_id: nodeId });
  if (at) q.set("at", at);
  const res = await fetch(`${API}/impact?${q}`);
  if (!res.ok) throw new Error("impact failed");
  return res.json();
}

export async function reroute(sourceId: string, targetId: string): Promise<Reroute> {
  const res = await fetch(`${API}/reroute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_id: sourceId, target_id: targetId }),
  });
  if (!res.ok) throw new Error("reroute failed");
  return res.json();
}

export function streamUrl(speed = 50): string {
  const base = API.replace(/^http/, "ws");
  return `${base}/ws/stream?speed=${speed}`;
}
