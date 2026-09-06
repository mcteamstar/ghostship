## Why

When `ga-portal` (Caddy) proxies dashboard port traffic to `gs-{crew_id}:5476`, the KiroCrew gateway rejects requests with **403 — IP mismatch**. The `mc_token_5476` session cookie is bound by KiroCrew to the IP that performed the token exchange. The transport mints the cookie from `ga-transport`'s container IP; Caddy proxies from `ga-portal`'s container IP. The gateway sees a different IP and rejects it. The old per-port uvicorn proxy worked because it ran inside `ga-transport` and made all upstream requests from the same IP as the cookie exchange.

## What Changes

- Add a `/crews/{crew_id}/ui/` reverse-proxy endpoint on the transport that injects `mc_token_5476` on every request and proxies to `gs-{crew_id}:5476`, running from the correct `ga-transport` IP.
- `ga-portal` routes per-crew dashboard port traffic to `ga-transport:{PORT}/crews/{crew_id}/ui/` rather than directly to `gs-{crew_id}:5476`.
- The transport proxy endpoint handles both HTTP and WebSocket upgrades — the same flows the old per-port proxy handled.
- Remove the `Cookie: mc_token_5476=...` header injection from the Caddy crew server config (`_caddy_register_crew`) — no longer needed since the transport handles it.
- Cookie refresh: when the token expires, the transport proxy endpoint re-mints it transparently.
- **Not breaking** — this is an internal routing change; `dashboard_url` shape and port allocation are unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/caddy-proxy`: The per-crew Caddy server routes to `ga-transport` (cookie-injecting proxy) rather than directly to `gs-{crew_id}:5476`. The transport's proxy endpoint handles the IP-bound cookie constraint.
- `transport/dashboard-proxy`: When `GA_PORTAL_ENABLED=true`, the transport exposes a lightweight proxy endpoint for each crew's dashboard port. Caddy routes to this endpoint; the transport injects the crew's session cookie and forwards to the crew gateway.

## Impact

- `transport/server.py` — add `GET|WS /crews/{crew_id}/ui/{path:path}` handler that injects `mc_token_5476` and proxies to `gs-{crew_id}:5476`
- `_caddy_register_crew` — route to `ga-transport:{PORT}/crews/{crew_id}/ui/` instead of `gs-{crew_id}:5476`; remove the `Cookie` header injection from Caddy config
- Token expiry — proxy endpoint calls `_mint_cookie` when the stored cookie is near expiry (> 80% of TTL elapsed) to keep sessions fresh
- No new config vars
- No deploy-time migration needed
