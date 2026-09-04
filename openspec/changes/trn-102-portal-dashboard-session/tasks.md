## 1. Transport proxy endpoint

- [ ] 1.1 Add `GET /crews/{crew_id}/ui/{path:path}` handler to `transport/server.py`:
  - Look up crew in registry; return 404 if missing or has no `dashboard_port`
  - Inject `Cookie: mc_token_5476={crew['cookie']}` on forwarded request to `gs-{crew_id}:5476/{path}`
  - Strip hop-by-hop headers; stream response body back
  - Return 503 if `GA_PORTAL_ENABLED=false`
- [ ] 1.2 Add WebSocket upgrade path in the same handler:
  - Detect `Upgrade: websocket` header; use `httpx-ws.aconnect_ws` to relay frames bidirectionally
  - Handle disconnect gracefully on either side
- [ ] 1.3 Add token refresh: decode JWT `exp` from `crew['cookie']`; if < 20% TTL remaining, call `_mint_cookie` and update registry before forwarding
- [ ] 1.4 Register the handler in the route table alongside other `/crews/*` endpoints

## 2. Update `_caddy_register_crew`

- [ ] 2.1 Change the crew `reverse_proxy` upstream from `gs-{crew_id}:5476` to `ga-transport:{PORT}/crews/{crew_id}/ui/`
- [ ] 2.2 Remove the `Cookie` header injection from the Caddy crew proxy config (now handled by the transport)
- [ ] 2.3 Update the docstring to reflect the new routing

## 3. Tests

- [ ] 3.1 Unit test: `GET /crews/{crew_id}/ui/` injects `mc_token_5476` cookie on forwarded request
- [ ] 3.2 Unit test: handler returns 404 for unknown crew, 503 when `GA_PORTAL_ENABLED=false`
- [ ] 3.3 Unit test: `_caddy_register_crew` no longer includes `Cookie` in Caddy config; upstream is `ga-transport:{PORT}`
- [ ] 3.4 Run `tests/run.sh --unit` — all tests pass

## 4. CORS and docs

- [ ] 4.1 Verify `KIROCREW_CORS_ORIGINS` — the proxy endpoint is served from the transport's port (8000), not port 64058. Check whether the existing CORS origin injection at container create time covers the transport's external URL; update if needed so the SPA's API calls are not rejected
- [ ] 4.2 Update `docs/dashboard-proxy.md` to describe the transport-proxy routing
- [ ] 4.3 Close TRN-102 notes about IP mismatch being resolved
