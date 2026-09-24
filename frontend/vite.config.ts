import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
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
