## Context

See proposal.md — Problem and Root cause. `CaddyPortal.register_crew` in `transport/caddy.py` builds a crew dashboard server with a single route whose handler list is `[forward_auth_handler, crew_proxy_handler]`. Caddy's `handle_response`-based `forward_auth` fires its subrequest as a plain HTTP GET; for a browser WebSocket upgrade (`Connection: Upgrade`) this discards the upgrade and the handshake silently fails. The fix is confined to how the Caddy JSON server object is assembled at registration time — no transport-process code path, API, or MCP surface changes.

Constraints that shape the approach:
- Caddy evaluates `server.routes` in order; the first route whose matcher matches handles the request. Routes without a matcher match everything.
- The transport UI-proxy endpoint (`/crews/{crew_id}/ui/`) already upgrades and relays WebSocket frames (see dashboard-proxy spec). The only thing in the way is the edge `forward_auth` on the dashboard port.
- `X-Transport-Token` injection lives on `crew_proxy_handler`, so reusing that handler on both routes keeps the header on every forwarded request automatically.

## Goals / Non-Goals

**Goals:**
- WebSocket upgrade requests on a crew dashboard port reach the transport UI proxy without passing through `forward_auth`.
- Plain-HTTP requests retain the existing `forward_auth`-gated behaviour unchanged.
- The split is observable in the registered server object so it can be unit-tested without a live Caddy.

**Non-Goals:**
- Changing authentication semantics for the initial HTTP page load (still `forward_auth`-gated).
- Any change to the transport UI-proxy endpoint, cookie injection, or token refresh.
- Reworking the main-server MCP/file routes — this touches only per-crew dashboard servers.

## Decisions

**Decision: Split the single route into an ordered pair — WS-matched route first, HTTP catch-all second.**
`register_crew` builds `server_obj["routes"]` as:
1. `{"match": [{"header": {"Connection": ["Upgrade"]}}], "handle": [crew_proxy_handler]}`
2. `{"handle": [forward_auth_handler, crew_proxy_handler]}` (no matcher; `[crew_proxy_handler]` only when `self._api_key` is unset)

Rationale: a header matcher on `Connection: Upgrade` is the narrowest reliable signal that distinguishes a WebSocket handshake from ordinary traffic, and Caddy's native WS proxying keys off the same header. Ordering the WS route first guarantees upgrades never fall through to the `forward_auth` path.

*Alternative considered — keep one route and set `forward_auth` to skip on upgrade:* Caddy's `forward_auth` has no built-in "skip when upgrading" switch; emulating it would require a response matcher gymnastics that is more fragile than two explicit routes. Rejected.

*Alternative considered — a path matcher on the WS endpoint (`/api/ws`):* couples the proxy config to a specific SPA route and breaks if the SPA adds another WS endpoint. The `Connection: Upgrade` header is route-agnostic and future-proof. Rejected.

**Decision: Reuse the existing `crew_proxy_handler` object on both routes.**
It already carries the `ga-transport:{PORT}` dial, the `/crews/{crew_id}/ui/{path}` rewrite, and the `X-Transport-Token` header injection, so both routes inherit identical upstream behaviour and the header requirement in the caddy-proxy spec holds without a second handler definition.

**Decision: The WS route carries no `forward_auth`, by design.**
Security rationale is in proposal.md — Impact: reaching the dashboard port at all required the `gs_session` validated on the SPA's initial HTTP load, which was `forward_auth`-gated. The WS connection inherits that authenticated context; it is not a new unauthenticated entry point.

## Risks / Trade-offs

- **A non-browser client could craft `Connection: Upgrade` to skip `forward_auth` and reach the UI proxy.** → The UI proxy only speaks the crew gateway's WebSocket protocol over an already-authenticated cookie context; a bare upgrade with no valid `mc_token_5476` is rejected downstream by the gateway (403 → cookie refresh path). The dashboard port is also not a public ingress by default. Residual risk is equivalent to the pre-existing WS exposure of the proxy endpoint itself.
- **Route ordering regression.** → If a future edit reorders routes and the catch-all precedes the WS route, upgrades break again. Mitigation: the unit test (tasks 3.1) asserts both the presence of the WS route and its position before the catch-all.
- **`forward_auth` handler shape differs across Caddy versions.** → The split only moves an existing, already-working handler between routes; it does not change the handler's internals, so version compatibility is unaffected.

## Migration Plan

1. Ship the `register_crew` change; it only affects server objects registered *after* deploy.
2. On transport startup, `_reconcile_registry` re-registers every crew's dashboard server, so existing crews pick up the two-route layout without manual intervention (idempotent per the caddy-proxy re-registration requirement).
3. Rollback: revert `transport/caddy.py`; the next transport restart re-registers single-route servers. No data migration, no persisted state change — the Caddy config is rebuilt from `crews.json` on every start.
