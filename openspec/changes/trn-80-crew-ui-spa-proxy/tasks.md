## 1. CORS origin injection at container create

- [ ] 1.1 In `transport/server.py` `container_create` block (around line 1816), derive the transport's public origin from `GA_HOST_URL` (strip trailing slash, use scheme+host only) or fall back to `http://localhost:{PORT}`
- [ ] 1.2 Append the public origin to `KIROCREW_CORS_ORIGINS`, comma-separated, preserving any pre-existing value from the composition env
- [ ] 1.3 Add unit tests: CORS origin injected correctly when `GA_HOST_URL` is set; when unset; when a pre-existing value is present (append, not replace)

## 2. crew_ui_context cookie on UI proxy response

- [ ] 2.1 In `_handle_crew_ui_proxy` (server.py:659), after streaming the upstream response back, set a `crew_ui_context={crew_id}` cookie: `HttpOnly`, `SameSite=Strict`, `Path=/`, `Max-Age=3600`
- [ ] 2.2 Only set the cookie when the matched route is the root UI path (`/crews/{id}/ui` or `/crews/{id}/ui/`), not on sub-path asset requests that happen to go through the proxy
- [ ] 2.3 Add unit test: response from `/crews/{id}/ui/` includes the `Set-Cookie` header with correct attributes

## 3. Catch-all SPA asset re-routing

- [ ] 3.1 Add a catch-all `GET /{path:path}` route to the transport at lowest priority (after all existing specific routes)
- [ ] 3.2 In the catch-all handler, extract `Referer` from the request headers; if it matches `/crews/{crew_id}/ui/` (or any sub-path), proxy the request to `http://gs-{crew_id}:{PORT}/{path}?{query}` via the existing proxy logic
- [ ] 3.3 If `Referer` is absent or doesn't match, fall back to `crew_ui_context` cookie; proxy to the crew identified by the cookie value
- [ ] 3.4 If neither Referer nor cookie identifies a valid crew, return 404 with `"No crew context for SPA asset request"`
- [ ] 3.5 Ensure the catch-all is never invoked for paths that match existing transport routes (MCP, files, login, crews API, health)
- [ ] 3.6 Add unit tests: Referer match proxies to correct crew; cookie fallback works; no Referer + no cookie returns 404; existing route paths are NOT intercepted by catch-all

## 4. Spec sync and validation

- [ ] 4.1 Merge `openspec/changes/trn-80-crew-ui-spa-proxy/specs/proxy-hosting/spec.md` delta into `openspec/specs/proxy-hosting/spec.md`
- [ ] 4.2 Create `openspec/specs/crew-ui-spa-routing/spec.md` from the change spec
- [ ] 4.3 Run `openspec validate` and confirm no errors
