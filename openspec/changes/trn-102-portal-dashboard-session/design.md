## Context

See proposal.md for the IP binding root cause.

The KiroCrew gateway binds `mc_token_5476` to the client IP that performed the token exchange. `_mint_cookie()` in the transport runs `kirocrew token --ttl 24h` inside the crew container and then makes an HTTP GET to `gs-{crew_id}:5476/?token=...` from `ga-transport`'s IP. The resulting session cookie is bound to that IP. When `ga-portal` proxies requests directly to `gs-{crew_id}:5476`, they arrive from `ga-portal`'s IP and the gateway returns 403.

The fix is to route dashboard proxy traffic through the transport, which is already on the correct IP.

## Goals / Non-Goals

**Goals:**
- Dashboard loads authenticated when accessed via `ga-portal`
- WebSocket connections work (for real-time chat/task streaming)
- Token expiry handled without user-visible interruption

**Non-Goals:**
- Changing the port allocation model or `dashboard_url` shape
- Implementing a full new proxy framework — reuse existing httpx async client patterns

## Design

### New endpoint: `GET /crews/{crew_id}/ui/{path:path}`

Add a catch-all HTTP handler on the transport that:
1. Loads the crew from the registry; returns 404 if not found
2. Looks up the crew's `cookie`; if near expiry, re-mints via `_mint_cookie`
3. Forwards the request to `http://gs-{crew_id}:{CREW_GATEWAY_PORT}/{path}` with `Cookie: mc_token_5476={cookie}` injected
4. For WebSocket upgrade requests (`Upgrade: websocket`), proxies the WS connection bidirectionally using `httpx-ws`
5. Strips hop-by-hop headers; copies response headers and body back to the browser

This is essentially the old `_proxy_handler` and `_handle_dashboard_ws_proxy` logic from the removed per-port uvicorn threads, unified into a single transport route.

### Updated `_caddy_register_crew`

Change the crew `reverse_proxy` upstream from `gs-{crew_id}:5476` to `ga-transport:{PORT}/crews/{crew_id}/ui`. Remove the `Cookie` header injection from the Caddy config entirely.

The Caddy config for an open-access deployment becomes simply:
```json
{
  "handler": "reverse_proxy",
  "upstreams": [{"dial": "ga-transport:8000"}],
  "rewrite": {"uri": "/crews/{crew_id}/ui/"}
}
```

For a keyed deployment, the `forward_auth` check remains before this.

### Token refresh

Check `created_at` of the crew entry or the JWT `exp` field. If the cookie will expire within 20% of its TTL, call `_mint_cookie` synchronously before forwarding. Since requests are infrequent relative to the 24h TTL this is acceptable; a background refresh thread is not needed.

## Risks / Trade-offs

- **Transport as proxy again** — TRN-101 explicitly removed the per-port uvicorn machinery to clean up the transport. This re-adds proxying but in a single unified endpoint rather than per-port daemon threads. The architectural boundary is clearer: Caddy owns port binding and TLS; the transport owns the cookie-authenticated last mile to the crew gateway.
- **Single endpoint vs per-port** — the old design allocated a separate uvicorn server per crew; this uses one route with a `crew_id` path param. Much simpler, no daemon threads.
- **JWT parsing for expiry** — simple base64 decode of the payload, no signature verification needed (we trust our own tokens).
