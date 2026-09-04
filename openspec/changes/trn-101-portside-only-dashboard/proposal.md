## Why

The transport's per-port uvicorn proxy threads are a workaround that TRN-92 already replaced with `ga-portside`. Keeping them means the transport is in the proxying business twice over — once via its own threads, once via Portside — and operators get a worse-than-Portside experience (no TLS, no auth, broken SPA routing in edge cases) if they use `launch(dashboard=True)` without enabling Portside.

## What Changes

- **BREAKING**: `launch(dashboard=True)` requires `GA_PORTSIDE_ENABLED=true`. When Portside is disabled, `dashboard=True` is rejected with a clear error: `"dashboard access requires GA_PORTSIDE_ENABLED=true — see docs/dashboard-proxy.md"`.
- **Remove** the per-port uvicorn listener machinery from the transport: `_start_dashboard_port_server`, `_stop_dashboard_port_server`, `_dashboard_app`, the associated daemon-thread pool, and the `POST/DELETE /crews/{id}/dashboard` HTTP endpoints that manage them.
- **Remove** `GA_DASHBOARD_PORT_ENABLED` as an independent config flag — port allocation is now entirely Portside's concern. The dashboard port range config (`GA_DASHBOARD_PORT_RANGE_START`, `GA_DASHBOARD_PORT_COUNT`) is retained since Portside still uses it via the transport's port pool.
- The Portside path (`_caddy_register_crew`, `_caddy_deregister_crew`) becomes the sole dashboard proxy implementation.
- `docs/dashboard-proxy.md` updated to reflect Portside-only dashboard access.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/dashboard-proxy`: The per-port transport proxy mode is removed. `GA_PORTSIDE_ENABLED=true` is now required for dashboard access. `launch(dashboard=True)` with Portside disabled returns an error.

## Impact

- `transport/server.py` — remove `_start_dashboard_port_server`, `_stop_dashboard_port_server`, `_dashboard_app`, related daemon-thread machinery, `POST/DELETE /crews/{id}/dashboard` handlers.
- `transport/config.py` — remove `ga_dashboard_port_enabled` field (or repurpose as Portside-only gate).
- `docs/dashboard-proxy.md` — update.
- Tests — remove or update per-port proxy tests; add test for error when `dashboard=True` without Portside.
- **Breaking** — any operator using `launch(dashboard=True)` without `GA_PORTSIDE_ENABLED=true` will receive an error and need to enable Portside.
