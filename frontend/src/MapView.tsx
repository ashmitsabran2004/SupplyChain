import { useEffect, useRef, useState } from "react";
import type { GeoJSONSource, Map as MapboxMap, Popup } from "mapbox-gl";
import type { Reroute } from "./api";
import SvgNetworkMap from "./SvgNetworkMap";

type Props = {
  token: string;
  graph: GeoJSON.FeatureCollection;
  onNode: (id: string) => void;
  showCritical: boolean;
  highlight: Set<string>;
  waveNodes: Set<string>;
  showReroute: boolean;
  route: Reroute | null;
  showHeat: boolean; showEdges: boolean; showNodes: boolean; searchTarget: string | null;
};

const emptyFc = (): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features: [] });
const lineFrom = (legs: { lng: number; lat: number }[]): GeoJSON.Feature => ({
  type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: legs.map((leg) => [leg.lng, leg.lat]) },
});

export default function MapView({ token, graph, onNode, showCritical, highlight, waveNodes, showReroute, route, showHeat, showEdges, showNodes, searchTarget }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapboxMap | null>(null);
  const onNodeRef = useRef(onNode);
  const popupRef = useRef<Popup | null>(null);
  const [mapLoading, setMapLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  useEffect(() => { onNodeRef.current = onNode; }, [onNode]);

  useEffect(() => {
    let disposed = false;
    let initialized = false;
    let failed = false;
    let map: MapboxMap | null = null;

    const fail = (message: string, error?: unknown) => {
      if (disposed || failed) return;
      failed = true;
      console.error(`[ChainSight] ${message}`, error ?? "No additional error details");
      setFailure(message);
      setMapLoading(false);
      try {
        map?.remove();
      } catch (removeError) {
        console.error("[ChainSight] Mapbox cleanup failed after renderer fallback.", removeError);
      }
      map = null;
      mapRef.current = null;
    };

    if (!token || token.includes("replace_me")) {
      fail("Mapbox token is missing or still a placeholder.");
      return () => { disposed = true; };
    }

    try {
      const probe = document.createElement("canvas");
      if (!probe.getContext("webgl2")) {
        fail("WebGL2 is unavailable in this browser; displaying the SVG network instead.");
        return () => { disposed = true; };
      }
      if (!container.current) throw new Error("Map container element is unavailable.");
      const { width, height } = container.current.getBoundingClientRect();
      if (width <= 0 || height <= 0) throw new Error(`Map container has no drawable size (${width} × ${height}).`);
    } catch (error) {
      fail("Mapbox cannot initialize; displaying the SVG network instead.", error);
      return () => { disposed = true; };
    }

    const initializeLayers = (created: MapboxMap) => {
      if (disposed || initialized) return;
      initialized = true;
      try {
        created.resize();
        const nodeFeatures = graph.features.filter((feature) => feature.geometry.type === "Point");
        created.addSource("nodes", {
          type: "geojson",
          data: { type: "FeatureCollection", features: nodeFeatures },
          cluster: true,
          clusterMaxZoom: 4,
          clusterRadius: 45,
          clusterProperties: { riskTotal: ["+", ["accumulated"], ["get", "predicted_risk"]] },
        });
        created.addSource("heat-nodes", { type: "geojson", data: { type: "FeatureCollection", features: nodeFeatures } });
        created.addSource("edges", { type: "geojson", data: emptyFc() });
        created.addSource("orig-route", { type: "geojson", data: emptyFc() });
        created.addSource("alt-route", { type: "geojson", data: emptyFc() });
        created.addLayer({ id: "risk-heat", type: "heatmap", source: "heat-nodes", maxzoom: 6, paint: { "heatmap-weight": ["get", "predicted_risk"], "heatmap-intensity": 1.1, "heatmap-radius": 32, "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.2, "#12355b", 0.45, "#3de0c5", 0.7, "#ffb020", 1, "#ff4d6d"] } });
        created.addLayer({ id: "edges", type: "line", source: "edges", paint: { "line-color": ["interpolate", ["linear"], ["get", "predicted_risk"], 0.05, "#1f3b63", 0.35, "#6ea8ff", 0.7, "#ffb020", 1, "#ff4d6d"], "line-width": 1.1, "line-opacity": 0.45 } });
        created.addLayer({ id: "clusters", type: "circle", source: "nodes", filter: ["has", "point_count"], paint: {
          "circle-radius": ["step", ["get", "point_count"], 14, 10, 19, 30, 25],
          "circle-color": ["interpolate", ["linear"], ["/", ["get", "riskTotal"], ["get", "point_count"]], 0.1, "#3de0c5", 0.45, "#ffb020", 0.8, "#ff4d6d"],
          "circle-stroke-color": "#d7e3f7", "circle-stroke-width": 1.5,
        } });
        created.addLayer({ id: "cluster-count", type: "symbol", source: "nodes", filter: ["has", "point_count"], layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 11 }, paint: { "text-color": "#071018" } });
        created.addLayer({ id: "nodes", type: "circle", source: "nodes", filter: ["!", ["has", "point_count"]], paint: { "circle-radius": ["interpolate", ["linear"], ["get", "predicted_risk"], 0, 3.2, 1, 9], "circle-color": ["interpolate", ["linear"], ["get", "predicted_risk"], 0.1, "#3de0c5", 0.45, "#ffb020", 0.8, "#ff4d6d"], "circle-stroke-width": 1, "circle-stroke-color": "#071018" } });
        created.addLayer({ id: "critical", type: "circle", source: "nodes", filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "critical"], true]], layout: { visibility: "none" }, paint: { "circle-radius": 11, "circle-color": "transparent", "circle-stroke-width": 2, "circle-stroke-color": "#3de0c5" } });
        created.addLayer({ id: "cascade", type: "circle", source: "nodes", filter: ["in", "id", ""], paint: { "circle-radius": 13, "circle-color": "#ff4d6d", "circle-opacity": 0.25, "circle-stroke-color": "#ff4d6d", "circle-stroke-width": 2 } });
        created.addLayer({ id: "wave-pulse", type: "circle", source: "nodes", filter: ["in", "id", ""], paint: { "circle-radius": 18, "circle-color": "transparent", "circle-stroke-color": "#ffb020", "circle-stroke-width": 2.5, "circle-opacity": 0.9 } });
        created.addLayer({ id: "orig-route", type: "line", source: "orig-route", paint: { "line-color": "#ff8fa3", "line-width": 3.5, "line-dasharray": [1.4, 1.2] } });
        created.addLayer({ id: "alt-route", type: "line", source: "alt-route", paint: { "line-color": "#3de0c5", "line-width": 3.5 } });
        created.on("click", "nodes", (event) => {
          const id = event.features?.[0]?.properties?.id as string | undefined;
          if (id) onNodeRef.current(id);
        });
        created.on("mousemove", "nodes", (event) => {
          const feature = event.features?.[0];
          if (!feature || feature.geometry.type !== "Point") return;
          const props = feature.properties ?? {};
          const rank = [...graph.features].filter((item) => item.geometry.type === "Point").sort((a, b) => Number(b.properties?.betweenness_norm ?? b.properties?.betweenness ?? 0) - Number(a.properties?.betweenness_norm ?? a.properties?.betweenness ?? 0)).findIndex((item) => item.properties?.id === props.id) + 1;
          const content = document.createElement("div");
          content.textContent = `${String(props.name ?? props.id)} · ${String(props.kind ?? "node")} · risk ${Number(props.predicted_risk ?? 0).toFixed(2)} · capacity ${String(props.capacity ?? "unknown")} · centrality rank ${rank || "unranked"}`;
          popupRef.current?.setLngLat(feature.geometry.coordinates as [number, number]).setDOMContent(content).addTo(created);
        });
        created.on("mouseleave", "nodes", () => popupRef.current?.remove());
        created.on("click", "clusters", (event) => {
          const feature = event.features?.[0];
          const clusterId = feature?.properties?.cluster_id;
          const coordinates = feature?.geometry.type === "Point" ? feature.geometry.coordinates as [number, number] : null;
          if (clusterId === undefined || !coordinates) return;
          const source = created.getSource("nodes") as GeoJSONSource;
          source.getClusterExpansionZoom(Number(clusterId), (error, zoom) => {
            if (!error && zoom !== undefined && zoom !== null) created.easeTo({ center: coordinates, zoom });
          });
        });
        created.on("mouseenter", "clusters", () => { created.getCanvas().style.cursor = "pointer"; });
        created.on("mouseleave", "clusters", () => { created.getCanvas().style.cursor = ""; });
        created.getCanvas().style.cursor = "pointer";
        setMapLoading(false);
      } catch (error) {
        fail("Mapbox style setup failed; displaying the SVG network instead.", error);
      }
    };

    void (async () => {
      try {
        const [mod] = await Promise.all([import("mapbox-gl/esm"), import("mapbox-gl/dist/mapbox-gl.css")]);
        if (disposed || !container.current) return;
        mod.setAccessToken(token);
        const created = new mod.Map({
          container: container.current,
          style: "mapbox://styles/mapbox/dark-v11",
          center: [54, 22],
          zoom: 1.55,
          projection: "globe",
        }) as unknown as MapboxMap;
        map = created;
        mapRef.current = created;
        popupRef.current = new mod.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: "chainsight-tooltip" }) as unknown as Popup;
        created.on("error", (event) => fail("Mapbox reported a style, tile, worker, or rendering error; displaying the SVG network instead.", event.error));
        created.on("style.load", () => initializeLayers(created));
        created.getCanvas().addEventListener("webglcontextlost", (event) => {
          event.preventDefault();
          fail("WebGL context was lost; displaying the SVG network instead.");
        });
      } catch (error) {
        fail("Mapbox failed to load or initialize; displaying the SVG network instead.", error);
      }
    })();

    return () => {
      disposed = true;
      map?.remove();
      mapRef.current = null;
    };
  }, [token]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("nodes")) return;
    const points = { type: "FeatureCollection" as const, features: graph.features.filter((feature) => feature.geometry.type === "Point") };
    (map.getSource("nodes") as GeoJSONSource).setData(points);
    (map.getSource("heat-nodes") as GeoJSONSource).setData(points);
    (map.getSource("edges") as GeoJSONSource).setData({ type: "FeatureCollection", features: graph.features.filter((feature) => feature.geometry.type === "LineString") });
  }, [graph, mapLoading]);
  useEffect(() => { const map = mapRef.current; if (map?.getLayer("critical")) map.setLayoutProperty("critical", "visibility", showCritical ? "visible" : "none"); }, [showCritical, mapLoading]);
  useEffect(() => { const map = mapRef.current; if (!map) return; [["risk-heat", showHeat], ["edges", showEdges], ["nodes", showNodes], ["clusters", showNodes], ["cluster-count", showNodes], ["critical", showNodes && showCritical], ["cascade", showNodes], ["wave-pulse", showNodes && waveNodes.size > 0]].forEach(([id, visible]) => { if (map.getLayer(id as string)) map.setLayoutProperty(id as string, "visibility", visible ? "visible" : "none"); }); }, [showHeat, showEdges, showNodes, showCritical, waveNodes, mapLoading]);
  useEffect(() => { const map = mapRef.current; if (!map || !searchTarget) return; const feature = graph.features.find((item) => item.geometry.type === "Point" && item.properties?.id === searchTarget); if (feature?.geometry.type === "Point") map.flyTo({ center: feature.geometry.coordinates as [number, number], zoom: 5, essential: true }); }, [searchTarget, graph]);
  useEffect(() => { const map = mapRef.current; if (map?.getLayer("cascade")) map.setFilter("cascade", highlight.size ? ["in", "id", ...Array.from(highlight)] : ["in", "id", ""]); }, [highlight, mapLoading]);
  useEffect(() => { const map = mapRef.current; if (map?.getLayer("wave-pulse")) map.setFilter("wave-pulse", waveNodes.size ? ["in", "id", ...Array.from(waveNodes)] : ["in", "id", ""]); }, [waveNodes, mapLoading]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("orig-route")) return;
    (map.getSource("orig-route") as GeoJSONSource).setData(showReroute && route ? { type: "FeatureCollection", features: [lineFrom(route.original.legs)] } : emptyFc());
    (map.getSource("alt-route") as GeoJSONSource).setData(showReroute && route ? { type: "FeatureCollection", features: [lineFrom(route.alternative.legs)] } : emptyFc());
  }, [route, showReroute, mapLoading]);

  if (failure) return <SvgNetworkMap graph={graph} onNode={onNode} showCritical={showCritical} highlight={highlight} waveNodes={waveNodes} showReroute={showReroute} route={route} failureMessage={failure} showHeat={showHeat} showEdges={showEdges} showNodes={showNodes} searchTarget={searchTarget} />;
  return <><div ref={container} className="map" />{mapLoading && <div className="map-loading" role="status" aria-live="polite">Loading map…</div>}</>;
}
