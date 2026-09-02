## 1. Transport config ✓

- [x] 1.1 `GA_UI_PORT_RANGE_START` (default 64058), `GA_UI_PORT_RANGE_SIZE` (default 50), `GA_UI_PORT_ENABLED` (default true) in `transport/config.py`
- [x] 1.2 Env var entries in `scripts/install.sh` compose template

## 2. Podman port binding reverted ✓

- [x] 2.1 `ports` parameter removed from `transport/podman.py` `container_create`
- [x] 2.2 No `_container_ports` in `launch()`

## 3. Per-port uvicorn listener management ✓

- [x] 3.1 `_ui_port_servers`, `_ui_port_crew`, `_ui_app` module-level dicts
- [x] 3.2 `_start_ui_port_server(port, crew_id)` — daemon thread, own event loop
- [x] 3.3 `_stop_ui_port_server(port)` — sets `should_exit`, cleans up dicts
- [x] 3.4 Startup reconciliation re-starts listeners from registry

## 4. Port-based catch-all proxy handler ✓

- [x] 4.1 Catch-all in `BearerAuthMiddleware` reads `scope["server"][1]` for incoming port
- [x] 4.2 Fires only after all transport routes checked
- [x] 4.3 `_sanitise_query_string` applied to upstream URL
- [x] 4.4 Fresh `httpx.AsyncClient()` per request (daemon thread has own event loop)
- [x] 4.5 Session cookie (`mc_token_5476`) injected as `Set-Cookie` on responses
- [x] 4.6 `content-encoding` / `content-length` stripped after httpx decompression

## 5. `launch` parameter + nuke

- [x] 5.1 Port allocation, `_start_ui_port_server`, registry write, `ui_url` in response
- [x] 5.2 Nuke stops listener and releases port
- [ ] 5.3 Add `dashboard: bool = False` parameter to `launch()` — gate port allocation on this flag instead of `GA_UI_PORT_ENABLED` alone

## 6. CORS origin injection ✓

- [x] 6.1 Transport public origin appended to `KIROCREW_CORS_ORIGINS` at container create
- [x] 6.2 UI port origin also appended after port allocation

## 7. REST API for retrofitting dashboard

- [ ] 7.1 `POST /crews/{crew_id}/dashboard` — allocate port + start listener for existing crew; return `{"ui_url": "..."}`; no-op if already active
- [ ] 7.2 `DELETE /crews/{crew_id}/dashboard` — stop listener + release port; return `{"ui_url": null}`; no-op if not active
- [ ] 7.3 Both routes respect `GA_API_KEY` auth and `GA_UI_PORT_ENABLED`
- [ ] 7.4 Unit tests for both endpoints

## 8. ohnomer/servers firewall ✓

- [x] 8.1 `ufw allow 64058:64107/tcp` in `ohnomer/servers/hyperv/academy/install.sh`

## 9. Tests

- [ ] 9.1 Unit test: `launch(dashboard=True)` allocates port and returns `ui_url`; `launch(dashboard=False)` does not
- [ ] 9.2 Existing tests: `_start_ui_port_server`, `_stop_ui_port_server`, catch-all handler (already passing — verify)

## 10. Spec sync and validation

- [ ] 10.1 Merge delta specs into main specs: `proxy-hosting`, `crew-lifecycle`
- [ ] 10.2 Create `openspec/specs/crew-ui-spa-routing/spec.md` from the change spec
- [ ] 10.3 Run `openspec validate` and confirm no errors
