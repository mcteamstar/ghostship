## Why

The transport's per-port uvicorn proxy threads are a workaround that TRN-92 already replaced with `ga-portal`. Keeping them means the transport is in the proxying business twice over — once via its own threads, once via Portal — and operators get a worse-than-Portal experience (no TLS, no auth, broken SPA routing in edge cases) if they use `launch(dashboard=True)` without enabling Portal.

## What Changes

- **BREAKING**: `launch(dashboard=True)` requires `GA_PORTAL_ENABLED=true`. When Portal is disabled, `dashboard=True` is rejected with a clear error: `"dashboard access requires GA_PORTAL_ENABLED=true — see docs/dashboard-proxy.md"`.
- **Remove** the per-port uvicorn listener machinery from the transport: `_start_dashboard_port_server`, `_stop_dashboard_port_server`, `_dashboard_app`, the associated daemon-thread pool, and the `POST/DELETE /crews/{id}/dashboard` HTTP endpoints that manage them.
- **Remove** `GA_DASHBOARD_PORT_ENABLED` as an independent config flag — port allocation is now entirely Portal's concern. The dashboard port range config (`GA_DASHBOARD_PORT_RANGE_START`, `GA_DASHBOARD_PORT_COUNT`) is retained since Portal still uses it via the transport's port pool.
- The Portal path (`_caddy_register_crew`, `_caddy_deregister_crew`) becomes the sole dashboard proxy implementation.
- `docs/dashboard-proxy.md` updated to reflect Portal-only dashboard access.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/dashboard-proxy`: The per-port transport proxy mode is removed. `GA_PORTAL_ENABLED=true` is now required for dashboard access. `launch(dashboard=True)` with Portal disabled returns an error.

## Impact

- `transport/server.py` — remove `_start_dashboard_port_server`, `_stop_dashboard_port_server`, `_dashboard_app`, related daemon-thread machinery, `POST/DELETE /crews/{id}/dashboard` handlers.
- `transport/config.py` — remove `ga_dashboard_port_enabled` field (or repurpose as Portal-only gate).
- `docs/dashboard-proxy.md` — update.
- Tests — remove or update per-port proxy tests; add test for error when `dashboard=True` without Portal.
- **Breaking** — any operator using `launch(dashboard=True)` without `GA_PORTAL_ENABLED=true` will receive an error and need to enable Portal.
