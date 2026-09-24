import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  worker: { format: "es" },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("mapbox-gl/dist/esm/core.js")) return "mapbox-core";
          if (id.includes("mapbox-gl/dist/esm/shared.js")) return "mapbox-shared";
          if (id.includes("node_modules/react-dom") || id.includes("node_modules/scheduler")) return "react-dom";
          if (id.includes("node_modules/react/")) return "react";
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/predict": "http://localhost:8000",
      "/simulate": "http://localhost:8000",
      "/reroute": "http://localhost:8000",
      "/impact": "http://localhost:8000",
      "/graph": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
