## Context

See proposal.md for motivation.

The per-port uvicorn proxy machinery currently in `transport/server.py`:
- `_dashboard_app` — the fully-wrapped Starlette app reference, set at startup
- `_start_dashboard_port_server(port, crew_id, app)` — starts a daemon-thread uvicorn server on `port`
- `_stop_dashboard_port_server(port)` — stops it
- `_handle_crew_dashboard_post/delete` — HTTP handlers for `POST/DELETE /crews/{id}/dashboard`
- Startup code at line 4438 that re-starts per-port listeners on container restart
- `GA_DASHBOARD_PORT_ENABLED` config flag that gates all of the above
- Call sites in `launch()` and `nuke()` that start/stop listeners

The Portside path (`_caddy_register_crew`, `_caddy_deregister_crew`) already handles everything when `GA_PORTSIDE_ENABLED=true` — it's complete and tested (TRN-92, 509 tests). The per-port machinery is dead weight when Portside is on, and a misleading (unauthenticated, plain HTTP) alternative when it's off.

## Goals / Non-Goals

**Goals:**
- `launch(dashboard=True)` returns a clear error when `GA_PORTSIDE_ENABLED=false`
- Remove all per-port uvicorn proxy code from the transport
- Port pool allocation stays — Portside still uses it via `_allocate_dashboard_port`

**Non-Goals:**
- Changing the Portside dashboard path — it's already correct
- Removing the dashboard port range config (`GA_DASHBOARD_PORT_RANGE_START`, `GA_DASHBOARD_PORT_COUNT`) — Portside needs them

## Decisions

**Reject `dashboard=True` when Portside is disabled, don't silently ignore it**

Returning `dashboard_url=null` silently would mask a misconfiguration. An operator who calls `launch(dashboard=True)` expects a dashboard URL back. A clear error sends them to the docs. This is the correct UX for a breaking change.

**Remove `GA_DASHBOARD_PORT_ENABLED` as an independent flag**

The flag originally guarded the per-port proxy feature. With that feature gone, the flag has no meaning. Dashboard availability is now solely controlled by `GA_PORTSIDE_ENABLED`. Remove the field from `Config` and the `from_env()` reader. Update `ghostship.conf.example` accordingly.

**Keep `POST/DELETE /crews/{id}/dashboard` routes but point them at the Portside path**

The routes exist and may be called by the MCP tool layer. Rather than removing the HTTP endpoints entirely, simplify them: `POST` allocates a port and calls `_caddy_register_crew` (errors if Portside disabled), `DELETE` calls `_caddy_deregister_crew`. Remove the uvicorn start/stop calls from both.

## Risks / Trade-offs

- **Breaking for operators using dashboards without Portside** — documented as breaking; migration is `GA_PORTSIDE_ENABLED=true` + reinstall.
- **Test churn** — the per-port proxy tests (TRN-80 era) need removal or update. The error-path test is new.

## Migration Plan

Existing deployments with `dashboard=True` crews and `GA_PORTSIDE_ENABLED=false`:
1. Set `GA_PORTSIDE_ENABLED=true` in `ghostship.conf`
2. Re-run `install.sh` — `ga-portside` is added to the compose stack, takes over dashboard ports
3. If `GA_PORTSIDE_TLS_MODE=internal` (default): run `caddy trust` once to trust the CA
4. Existing crews that had dashboard ports will need to be nuked and re-launched for Portside to register them
