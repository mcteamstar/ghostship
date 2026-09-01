## Context

See proposal.md — Why for motivation.

The KiroCrew gateway UI is a React SPA that uses root-absolute paths for assets, API calls, and client-side routing. It was designed to run at the root of an origin. Serving it under a path prefix (`/crews/{id}/ui/`) requires path stripping at the proxy layer so the SPA sees itself at `/`. Python-layer proxying can strip the path on the initial request but cannot intercept `window.history.pushState` calls that navigate the browser to `/chat` — once that happens, the browser URL no longer contains the crew path and subsequent requests are routed to the transport root.

Caddy is already running on vm23 as a reverse proxy in front of the transport (see `ohnomer/servers/hyperv/academy/`). Currently it has `admin off` and a read-only Caddyfile. The Caddy admin API (`localhost:2019`) supports adding and removing routes at runtime via JSON `PATCH` without reloading.

## Goals / Non-Goals

**Goals:**
- SPA assets, client-side navigation, and WebSocket connections all work correctly via the transport URL.
- Routes are registered/removed automatically at crew launch/nuke with no operator intervention.
- Graceful degradation: if Caddy admin is unreachable, launch/nuke succeed but log a warning; the UI is just unavailable via Caddy until it's fixed.

**Non-Goals:**
- TLS per-crew (all crews share the transport's existing TLS termination).
- Subdomain-per-crew routing.
- Supporting Caddy versions < 2.6 (admin API `PATCH` endpoint).

## Decisions

**D1: Caddy admin API for dynamic route management**

The transport calls `PATCH http://localhost:2019/config/apps/http/servers/srv0/routes` at launch to prepend a per-crew route block, and removes it by `DELETE`-ing the matching route at nuke time. Each route is a Caddy JSON fragment with a `handle_path` directive that strips `/crews/{id}/ui` and reverse-proxies to `http://gs-{id}:5476`.

Alternatives considered:
- *Rewrite Caddyfile on disk and reload*: requires file writes + `caddy reload` — brittle if the transport and Caddy are in different containers (they are). Admin API is cleaner and atomic.
- *Nginx with reload*: Nginx has no runtime API; requires config rewrite + `nginx -s reload`. More complex and less safe.
- *Per-crew sidecar proxy container*: one nginx/Caddy container per crew. Heavier, adds a container lifecycle dependency, more failure modes.

**D2: Route stored as JSON fragment in transport data dir**

Each live crew's Caddy route JSON is written to `<data_dir>/caddy_routes/<crew_id>.json` at launch. On transport startup, any route files present are re-registered with Caddy (handles transport restart without losing routes for live crews). At nuke, the file is removed.

**D3: GA_CADDY_UI_ENABLED flag + graceful degradation**

`GA_CADDY_UI_ENABLED=true` (default). When false, no Caddy registration is attempted and the old Python UI proxy (`_handle_crew_ui_proxy`) is preserved as-is. When true but the admin API is unreachable, launch/nuke log a warning and continue — the MCP tools still work, the crew UI via Caddy just won't be available until Caddy is fixed.

This lets the transport ship the change without breaking installs that haven't updated their Caddy config yet.

**D4: ohnomer/servers config changes**

In `install.sh`, change the Caddy global block from `admin off` to `admin localhost:2019`. Change the caddy.container volume mount from `:ro` to writable (drop `:ro`). These are the only deploy-side changes needed.

## Risks / Trade-offs

- **Route leakage if nuke fails mid-flight** → The route file in the data dir acts as a record. On startup, the transport re-registers all route files — so a leaked route for a nuked crew would try to re-register a non-existent upstream. Caddy won't error on this (the upstream just returns 502 until it's removed), but the transport should also attempt cleanup of stale route files (crew not in registry → remove from Caddy and delete file).
- **Caddy admin API not available on fresh install** → D3 handles this with `GA_CADDY_UI_ENABLED` and graceful degradation. Old Python proxy is the fallback until Caddy config is updated.
- **crew network isolation** → Caddy runs in host network mode, so `http://gs-{id}:5476` resolves via the Podman DNS on the ghost-academy network. This is the same hostname the transport already uses for all crew communication — no new network requirements.

## Migration Plan

1. Update `ohnomer/servers/hyperv/academy/install.sh`: enable admin, remove `:ro`.
2. Deploy to vm23 (`./deploy.sh academy`).
3. Existing live crews won't have Caddy routes — they need to be nuked and re-launched, or the transport startup reconciliation (D2) will register them on next restart.
4. Rollback: set `GA_CADDY_UI_ENABLED=false` — reverts to Python proxy without redeploying.
