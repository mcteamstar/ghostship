## 1. Transport config

- [x] 1.1 Confirm `GA_UI_PORT_RANGE_START` (default 64058), `GA_UI_PORT_RANGE_SIZE` (default 50), `GA_UI_PORT_ENABLED` (default true) are in `transport/config.py` (already added in previous iteration — verify)
- [x] 1.2 Confirm env var entries in `scripts/install.sh` compose template (already added — verify)

## 2. Remove Podman port binding (revert previous approach)

- [x] 2.1 Remove the `ports` parameter from `transport/podman.py` `container_create` — crew containers no longer bind host ports
- [x] 2.2 Remove any `_container_ports` / port-binding code from `launch()` in `transport/server.py`

## 3. Per-port uvicorn listener management

- [x] 3.1 Add `_ui_port_servers: dict[int, uvicorn.Server]` and `_ui_port_crew: dict[int, str]` module-level dicts to `transport/server.py`
- [x] 3.2 Write `_start_ui_port_server(port: int, crew_id: str)` — create a `uvicorn.Config` bound to `0.0.0.0:{port}` using the same Starlette app, start the server in the background event loop, store in `_ui_port_servers[port]`, store crew mapping in `_ui_port_crew[port]`
- [x] 3.3 Write `_stop_ui_port_server(port: int)` — set `server.should_exit = True`, wait briefly for shutdown, clean up both dicts
- [x] 3.4 On transport startup, for each crew in the registry with a `ui_port`, call `_start_ui_port_server` to restore listeners

## 4. Port-based catch-all proxy handler

- [x] 4.1 Add a catch-all route handler in `BearerAuthMiddleware` (or the Starlette app router) that fires when the incoming request port is in `_ui_port_crew` — look up the crew_id, proxy the full request (path + query) to `http://gs-{crew_id}:{CREW_GATEWAY_PORT}/{path}`
- [x] 4.2 The catch-all SHALL only fire after all existing transport routes are checked — transport's own MCP, files, login, etc. must not be shadowed
- [x] 4.3 Apply the existing `_sanitise_query_string` to the upstream URL

## 5. Wire into launch and nuke

- [x] 5.1 In `launch()`: when `GA_UI_PORT_ENABLED=True`, call `_allocate_ui_port()`, call `_start_ui_port_server(port, crew_id)`, store `ui_port` in registry, include `ui_url` in response
- [x] 5.2 In `nuke()` confirm=True path: when `GA_UI_PORT_ENABLED=True`, call `_stop_ui_port_server(crew["ui_port"])`, call `_release_ui_port()`
- [x] 5.3 When `GA_UI_PORT_ENABLED=False`: skip entirely

## 6. CORS origin injection

- [x] 6.1 In container_create env block: derive transport public origin from `GA_HOST_URL` or `http://localhost:{PORT}`, append to `KIROCREW_CORS_ORIGINS` (already implemented — verify it's still present after revert)

## 7. ohnomer/servers firewall

- [ ] 7.1 In `ohnomer/servers/hyperv/academy/install.sh`: add `ufw allow 64058:64107/tcp` so the transport's UI ports are reachable via Tailscale

## 8. Tests

- [ ] 8.1 Unit tests: `_start_ui_port_server` registers server and crew mapping; `_stop_ui_port_server` cleans up
- [ ] 8.2 Unit test: catch-all handler proxies to correct crew by incoming port
- [ ] 8.3 Unit test: launch response includes `ui_url`; crews list includes `ui_url`; nuke stops the listener
- [ ] 8.4 Unit test: `GA_UI_PORT_ENABLED=False` skips all listener management
- [ ] 8.5 Manual smoke test on vm23: launch a crew, open `ui_url` in browser, navigate to `/chat`, hard reload — confirm it renders correctly

## 9. Spec sync and validation

- [ ] 9.1 Merge delta specs into main specs: `proxy-hosting`, `crew-lifecycle`
- [ ] 9.2 Create `openspec/specs/crew-ui-spa-routing/spec.md` from the change spec
- [ ] 9.3 Run `openspec validate` and confirm no errors
