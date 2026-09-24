import { useEffect, useRef, useState } from "react";
import type { Map as MapboxMap, GeoJSONSource } from "mapbox-gl";
import type { Reroute } from "./api";

type Props = {
  token: string;
  graph: GeoJSON.FeatureCollection;
  onNode: (id: string) => void;
  showCritical: boolean;
  highlight: Set<string>;
  showReroute: boolean;
  route: Reroute | null;
};

const emptyFc = (): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features: [] });
const lineFrom = (legs: { lng: number; lat: number }[]): GeoJSON.Feature => ({
  type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: legs.map((l) => [l.lng, l.lat]) },
});

export default function MapView({ token, graph, onNode, showCritical, highlight, showReroute, route }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapboxMap | null>(null);
  const [mapLoading, setMapLoading] = useState(true);

  useEffect(() => {
    let disposed = false;
    let map: MapboxMap | null = null;
    void Promise.all([import("mapbox-gl/esm"), import("mapbox-gl/dist/mapbox-gl.css")]).then(([mod]) => {
      if (disposed || !container.current) return;
      mod.setAccessToken(token);
      const created = new mod.Map({ container: container.current, style: "mapbox://styles/mapbox/dark-v11", center: [54, 22], zoom: 1.55, projection: "globe" }) as unknown as MapboxMap;
      map = created;
      mapRef.current = created;
      created.on("load", () => {
        if (disposed) return;
        created.addSource("nodes", { type: "geojson", data: emptyFc() });
        created.addSource("edges", { type: "geojson", data: emptyFc() });
        created.addSource("orig-route", { type: "geojson", data: emptyFc() });
        created.addSource("alt-route", { type: "geojson", data: emptyFc() });
        created.addLayer({ id: "risk-heat", type: "heatmap", source: "nodes", maxzoom: 6, paint: { "heatmap-weight": ["get", "predicted_risk"], "heatmap-intensity": 1.1, "heatmap-radius": 32, "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.2, "#12355b", 0.45, "#3de0c5", 0.7, "#ffb020", 1, "#ff4d6d"] } });
        created.addLayer({ id: "edges", type: "line", source: "edges", paint: { "line-color": ["interpolate", ["linear"], ["get", "predicted_risk"], 0.05, "#1f3b63", 0.35, "#6ea8ff", 0.7, "#ffb020", 1, "#ff4d6d"], "line-width": 1.1, "line-opacity": 0.45 } });
        created.addLayer({ id: "nodes", type: "circle", source: "nodes", paint: { "circle-radius": ["interpolate", ["linear"], ["get", "predicted_risk"], 0, 3.2, 1, 9], "circle-color": ["interpolate", ["linear"], ["get", "predicted_risk"], 0.1, "#3de0c5", 0.45, "#ffb020", 0.8, "#ff4d6d"], "circle-stroke-width": 1, "circle-stroke-color": "#071018" } });
        created.addLayer({ id: "critical", type: "circle", source: "nodes", filter: ["==", ["get", "critical"], true], layout: { visibility: "none" }, paint: { "circle-radius": 11, "circle-color": "transparent", "circle-stroke-width": 2, "circle-stroke-color": "#3de0c5" } });
        created.addLayer({ id: "cascade", type: "circle", source: "nodes", filter: ["in", "id", ""], paint: { "circle-radius": 13, "circle-color": "#ff4d6d", "circle-opacity": 0.25, "circle-stroke-color": "#ff4d6d", "circle-stroke-width": 2 } });
        created.addLayer({ id: "orig-route", type: "line", source: "orig-route", paint: { "line-color": "#ff8fa3", "line-width": 3.5, "line-dasharray": [1.4, 1.2] } });
        created.addLayer({ id: "alt-route", type: "line", source: "alt-route", paint: { "line-color": "#3de0c5", "line-width": 3.5 } });
        created.on("click", "nodes", (e) => { const id = e.features?.[0]?.properties?.id as string | undefined; if (id) onNode(id); });
        created.getCanvas().style.cursor = "pointer";
        setMapLoading(false);
      });
    }).catch((error: unknown) => { console.error("Mapbox failed to load", error); setMapLoading(false); });
    return () => { disposed = true; map?.remove(); mapRef.current = null; };
  }, [token, onNode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("nodes")) return;
    (map.getSource("nodes") as GeoJSONSource).setData({ type: "FeatureCollection", features: graph.features.filter((f) => f.geometry.type === "Point") });
    (map.getSource("edges") as GeoJSONSource).setData({ type: "FeatureCollection", features: graph.features.filter((f) => f.geometry.type === "LineString") });
  }, [graph, mapLoading]);
  useEffect(() => { const m = mapRef.current; if (m?.getLayer("critical")) m.setLayoutProperty("critical", "visibility", showCritical ? "visible" : "none"); }, [showCritical, mapLoading]);
  useEffect(() => { const m = mapRef.current; if (m?.getLayer("cascade")) m.setFilter("cascade", highlight.size ? ["in", "id", ...Array.from(highlight)] : ["in", "id", ""]); }, [highlight, mapLoading]);
  useEffect(() => {
    const m = mapRef.current;
    if (!m?.getSource("orig-route")) return;
    (m.getSource("orig-route") as GeoJSONSource).setData(showReroute && route ? { type: "FeatureCollection", features: [lineFrom(route.original.legs)] } : emptyFc());
    (m.getSource("alt-route") as GeoJSONSource).setData(showReroute && route ? { type: "FeatureCollection", features: [lineFrom(route.alternative.legs)] } : emptyFc());
  }, [route, showReroute, mapLoading]);

  return <><div ref={container} className="map" />{mapLoading && <div className="map-loading" role="status" aria-live="polite">Loading map…</div>}</>;
}
