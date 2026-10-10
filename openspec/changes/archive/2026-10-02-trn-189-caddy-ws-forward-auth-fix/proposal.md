# TRN-189 — Caddy forward_auth blocks WebSocket upgrades on crew dashboard ports

## Problem

The per-crew Caddy dashboard server registered by `_caddy_register_crew` in
`transport/caddy.py` places `forward_auth` in front of `reverse_proxy` in a
single route. Caddy's `handle_response`-based forward_auth pattern cannot pass
through WebSocket upgrade requests — the subrequest fires as HTTP and the WS
upgrade is dropped, causing the browser to report:

```
Firefox can't establish a connection to the server at ws://<host>:<port>/api/ws
```

This breaks the KiroCrew SPA: the sessions list doesn't load, the import modal
can't be dismissed, and live task updates (which require the WS connection) stop
working.

## Root cause

`CaddyPortal.register_crew` builds a `server_obj` with a single route:

```python
routes = [{"handle": [forward_auth_handler, crew_proxy_handler]}]
```

Caddy processes handlers sequentially. When the browser sends a WS upgrade
(`Connection: Upgrade`), Caddy fires the `forward_auth` subrequest as a plain
HTTP GET to `/dashboard/auth`. The subrequest succeeds (2xx), but by then the
upgrade has not been preserved and the connection is never upgraded — the WS
handshake silently fails.

## Proposed fix

Split the single route into two in `register_crew`:

1. **WS route** — matcher `header: {Connection: [Upgrade]}` → `crew_proxy_handler` only (no forward_auth). WS connections inherit the authenticated browser context; the `gs_session` was validated on the HTTP request that loaded the SPA.
2. **HTTP route** — no matcher (catch-all) → `[forward_auth_handler, crew_proxy_handler]` (existing behaviour, unchanged).

Both routes still inject `X-Transport-Token`.

## Scope

- `transport/caddy.py` — `CaddyPortal.register_crew`: split `server_obj.routes` into WS + HTTP routes
- `openspec/specs/transport/caddy-proxy/spec.md` — add scenario for WS upgrade passthrough
- `openspec/specs/transport/dashboard-proxy/spec.md` — the existing WS scenario now correctly specifies this behaviour; no change needed
- Tests: update or add a unit test asserting the WS route is present in the registered server object

## Impact

- Fixes: KiroCrew SPA sessions list, live updates, import modal dismissal
- No security regression: WS connections on the dashboard port already require a valid `gs_session` to reach the port at all (Caddy's forward_auth gates the initial HTTP connection)
- No API or MCP tool changes
