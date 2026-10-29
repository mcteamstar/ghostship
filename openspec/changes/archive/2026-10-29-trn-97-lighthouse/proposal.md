## Why

Opening the ghostship portal URL in a browser returns nothing — `/` is unregistered
on the transport and not proxied by Caddy. Operators have no browser-accessible view
of fleet state; checking crew status, backend, last task, or mail requires an active
MCP agent session.

## What Changes

- `GET /` on the transport serves a single-file HTML+JS fleet dashboard (Lighthouse).
- `GET /api/crews` is added as a first-class REST endpoint on the transport (the
  fleet data currently exists only inside the MCP `crews()` tool).
- The SPA polls `/api/crews` every 5 s and renders a fleet status table; each crew
  row expands to show per-crew detail fetched from the existing `/crews/{id}/api/*`
  proxy.
- Caddy's main-port config gains a new `ga-lighthouse` route that session-gates `/`,
  `/api/crews*`, and `/crews/*/api/*` via the existing `forward_auth` →
  `reverse_proxy` chain (same `gs_session` cookie and `/dashboard/auth` check used
  for per-crew dashboards). Unauthenticated requests redirect to
  `/dashboard/login?next=/`. When `GA_API_KEY` is unset, the `forward_auth` check
  is omitted and requests proxy directly — no-key installs work without a login step.
- Auth reuses the existing `DashboardGate` session mechanism. No new auth mechanism.
  The operator logs in once at `/dashboard/login`; the browser carries the
  `gs_session` cookie on all subsequent SPA `fetch()` calls automatically.
- No new container, no new Compose service, no new Python dependency.

## Capabilities

### New Capabilities

- `transport/fleet-overview`: Fleet dashboard served at `/` by the transport.
  Covers the SPA delivery mechanism (inline HTML response handler), polling contract
  against `/api/crews`, per-crew detail expansion via the existing crew API proxy,
  and the bearer-auth gate at Caddy.

- `transport/crews-rest-api`: `GET /api/crews` as a bearer-gated REST endpoint
  returning the full fleet list — status, uptime_secs, last_task_at, acp_backend,
  composition, enrolled_agents, dashboard_url, gateway_healthy per crew, plus
  top-level host_memory_available_gb and active_crews.

### Modified Capabilities

- `transport/caddy-proxy`: The `ga-transport-misc` catch-all route must add `/`,
  `/api/crews*`, and `/crews/*/api/*` to its path matcher. Without this the portal
  does not forward these paths to the transport.

## Impact

- `transport/server.py`: new `GET /` and `GET /api/crews` handlers registered in
  `public_routes` of `BearerAuthMiddleware` (session enforcement is at the Caddy
  layer via `forward_auth`, same as `/crews/*/ui`).
- `transport/tools.py` (or new `transport/fleet.py`): crews data assembly extracted
  into a shared helper called by both the MCP tool and the REST handler.
- `bin/install.sh`: new `ga-lighthouse` Caddy route with `forward_auth` →
  `reverse_proxy` chain covering `/`, `/api/crews*`, `/crews/*/api/*`.
- `transport/openapi.py`: two new routes registered in the OpenAPI schema.
- `transport/dashboard-auth` capability: `DashboardGate`'s `/dashboard/auth`
  handler already supports the `forward_auth` pattern — no changes needed there,
  but the capability's spec should note that `/` is now a second consumer of this
  gate alongside the per-crew dashboard ports.
