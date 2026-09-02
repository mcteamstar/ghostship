## Why

The crew UI proxy works for the initial page load but breaks for SPA navigation: the KiroCrew gateway UI uses root-absolute paths for both static assets and client-side routing (e.g. navigates to `/chat`). Any approach that serves the SPA under a path prefix (`/crews/{id}/ui/`) cannot fix `window.history.pushState` navigation. The correct fix is to give each crew's UI its own origin. Found by Steve Mactaggart (stevemac007) in PR #3.

## What Changes

- **Opt-in at launch** — `launch(dashboard=True)` allocates a dedicated port from a configurable range (`GA_DASHBOARD_PORT_RANGE_START`, default 64058). Defaults to `False` — agent crews are headless by default, no ports opened.
- The transport (Python/uvicorn) binds an additional listener per crew in a daemon thread. All requests on that port are reverse-proxied to `http://gs-{crew_id}:5476/` over the internal ghost-academy Podman network. Crew containers are untouched.
- Because the transport handles all UI ports, `GA_API_KEY` auth and rate limiting apply automatically. No Caddy involvement, no direct Podman port bindings on crew containers.
- The transport injects the crew's session cookie (`mc_token_5476`) as `Set-Cookie` on proxied responses so the browser authenticates automatically.
- `KIROCREW_CORS_ORIGINS` is injected with both the transport's public origin and the UI port origin at container create time.
- A REST endpoint (`POST /crews/{crew_id}/dashboard`, `DELETE /crews/{crew_id}/dashboard`) allows retrofitting or removing a dashboard on an already-running crew without nuking its workspace.
- At nuke, the port listener is stopped and the port returned to the pool.
- `launch` response and `crews` list include `dashboard_url` when a dashboard is active (`null` otherwise).
- **Replaces** the previous path-prefix Python proxy (`/crews/{id}/ui/`), which broke SPA navigation.

## Capabilities

### New Capabilities

- `crew-ui-spa-routing`: Each crew's dashboard is served at its own port on the transport. The SPA owns its entire origin — assets, client-side navigation, and hard reloads all work. Opt-in at launch. Can be retrofitted via REST API.

### Modified Capabilities

- `crew-lifecycle`: `launch` gains a `dashboard` parameter; `nuke` stops any active listener.
- `proxy-hosting`: CORS injection updated to include UI port origin; crew UI proxy updated to describe per-port transport listeners and session cookie injection.

## Impact

- `transport/server.py` — `launch` gains `dashboard: bool = False`; port allocation, daemon-thread uvicorn servers, port-based catch-all proxy, session cookie injection, CORS origin injection.
- `transport/config.py` — `GA_DASHBOARD_PORT_RANGE_START` (default 64058), `GA_DASHBOARD_PORT_RANGE_SIZE` (default 50), `GA_DASHBOARD_PORT_ENABLED` (global on/off).
- `transport/server.py` — new REST routes `POST /crews/{crew_id}/dashboard` and `DELETE /crews/{crew_id}/dashboard`.
- `scripts/install.sh` — expose the UI port range via `ufw`; add env vars to compose template.
- No Caddy changes required. No MCP tool interface breaking changes.
