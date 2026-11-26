import { describe, expect, it } from "vitest";
import viteConfig from "../vite.config";

// The settings CONTRIBUTING.md and the image build depend on, read from the config
// itself: the dev proxy routes, the Host header it forwards, the /static/ base and
// the modulepreload polyfill that would otherwise inject an inline script.
const config = viteConfig as unknown as {
  base: string;
  server: { proxy: Record<string, { target: string; changeOrigin?: boolean }> };
  build: { modulePreload: { polyfill: boolean } };
};

describe("Vite configuration", () => {
  it("builds the bundle under /static/", () => {
    expect(config.base).toBe("/static/");
  });

  it("proxies /api, /crews and /dashboard to the portal named by RADAR_PROXY_TARGET", () => {
    const target = process.env.RADAR_PROXY_TARGET ?? "http://localhost:64057";
    for (const prefix of ["/api", "/crews", "/dashboard"]) {
      expect(config.server.proxy[prefix]?.target, prefix).toBe(target);
    }
  });

  it("forwards the browser's Host header unchanged, so the same-origin check still passes", () => {
    for (const prefix of ["/api", "/crews", "/dashboard"]) {
      expect(config.server.proxy[prefix]?.changeOrigin, prefix).not.toBe(true);
    }
  });

  it("disables the modulepreload polyfill, so index.html has no inline script", () => {
    expect(config.build.modulePreload.polyfill).toBe(false);
  });
});
