# TRN-189 Tasks

## 1. Fix `CaddyPortal.register_crew` in `transport/caddy.py`

- [ ] 1.1 Split `server_obj["routes"]` into two entries:
  - Route 1 (WS): matcher `{"header": {"Connection": ["Upgrade"]}}` → `[crew_proxy_handler]`
  - Route 2 (HTTP catch-all): no matcher → `[forward_auth_handler, crew_proxy_handler]` (or `[crew_proxy_handler]` when no API key)
- [ ] 1.2 Ensure both routes include `X-Transport-Token` injection (already on `crew_proxy_handler`)
- [ ] 1.3 Verify the fix applies when `self._api_key` is unset (HTTP-only path — only one route needed, WS route still needed)

## 2. Update caddy-proxy spec

- [ ] 2.1 Add scenario to `openspec/specs/transport/caddy-proxy/spec.md`:
  - **WHEN** the KiroCrew SPA opens a WebSocket connection through the dashboard port
  - **THEN** the Caddy server object has a route matching `Connection: Upgrade` that bypasses forward_auth and proxies directly to the transport UI proxy
  - **THEN** the WS connection is successfully upgraded

## 3. Tests

- [ ] 3.1 Add/update unit test in `tests/unit/` asserting that the `server_obj` returned by `register_crew` (when `api_key` is set) contains:
  - A route with a `Connection: Upgrade` header matcher and no forward_auth handler
  - A catch-all route with the forward_auth handler
- [ ] 3.2 Run full unit test suite and confirm pass

## 4. Deploy and validate

- [ ] 4.1 Deploy updated transport to academy
- [ ] 4.2 Launch a crew with `dashboard=True`, open dashboard in browser, confirm WS connects (`ws://` in browser devtools shows 101 Switching Protocols)
- [ ] 4.3 Confirm KiroCrew sessions list loads and live updates work
