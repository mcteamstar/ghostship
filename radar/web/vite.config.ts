import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The built bundle is served by ga-radar under /static/ (see radar/server.py and
// radar/Containerfile). Assets carry content hashes, so Vite's default
// `assets/<name>-<hash>.js` layout is what the cache policy depends on.
export default defineConfig({
  base: "/static/",
  plugins: [react()],
  build: {
    outDir: "dist",
    // No inline <script> in index.html: the modulepreload polyfill would add one.
    modulePreload: { polyfill: false },
    sourcemap: false,
  },
  server: {
    // Dev loop against a running fleet: Radar, the portal session and the crew
    // dashboards are all on the portal origin. Host is forwarded unchanged (no
    // changeOrigin) so the same-origin check on the refresh POST still passes.
    proxy: {
      "/api": { target: process.env.RADAR_PROXY_TARGET ?? "http://localhost:64057" },
      "/crews": { target: process.env.RADAR_PROXY_TARGET ?? "http://localhost:64057" },
      "/dashboard": { target: process.env.RADAR_PROXY_TARGET ?? "http://localhost:64057" },
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["test/setup.ts"],
    include: ["test/**/*.test.{ts,tsx}"],
    css: false,
  },
});
