## 1. Verify port binding behaviour

- [ ] 1.1 Confirm that Podman host port bindings set at `container_create` time persist across `container_stop` / `container_start` cycles — if not, port re-binding logic will be needed in `_ensure_crew_running`
- [ ] 1.2 Confirm that `podman.container_create` in `transport/podman.py` accepts a `ports` parameter and passes it correctly to the Podman API

## 2. Transport config

- [ ] 2.1 Add `GA_UI_PORT_RANGE_START` (default 9000), `GA_UI_PORT_RANGE_SIZE` (default 50), and `GA_UI_PORT_ENABLED` (default `true`) to `transport/config.py`
- [ ] 2.2 Add env var entries to `scripts/install.sh` compose template

## 3. Port allocation

- [ ] 3.1 Add module-level `_ui_ports_in_use: set[int]` to `transport/server.py`; populate from `crews.json` at startup
- [ ] 3.2 Write `_allocate_ui_port() -> int` — scan range for first port not in `_ui_ports_in_use`, add to set, return it; raise `RuntimeError` if range exhausted
- [ ] 3.3 Write `_release_ui_port(port: int)` — remove from `_ui_ports_in_use`

## 4. Wire into launch and nuke

- [ ] 4.1 In `launch` (when `GA_UI_PORT_ENABLED=true`): call `_allocate_ui_port()`, pass `ports={ui_port: 5476}` to `container_create`, store `ui_port` in the crew's `crews.json` entry, include `ui_url` in the launch response
- [ ] 4.2 In `nuke` (confirm=True, when `GA_UI_PORT_ENABLED=true`): call `_release_ui_port(crew["ui_port"])` and clear `ui_port` from the registry entry
- [ ] 4.3 When `GA_UI_PORT_ENABLED=false`: skip port allocation; existing `_handle_crew_ui_proxy` remains

## 5. Expose ui_url in crews list

- [ ] 5.1 In the `crews` tool, derive `ui_url` from `info.get("ui_port")` — `http://<GA_HOST_URL or localhost>:<ui_port>/` — and include it in each crew entry (`null` if no port assigned)

## 6. CORS origin injection

- [ ] 6.1 In `transport/server.py` `container_create` env block, derive the transport's public origin from `GA_HOST_URL` (scheme+host only) or fall back to `http://localhost:{PORT}`
- [ ] 6.2 Append the public origin to `KIROCREW_CORS_ORIGINS`, comma-separated, preserving any existing value
- [ ] 6.3 Add unit tests: CORS origin injected correctly when `GA_HOST_URL` is set; when unset; when a pre-existing value is present

## 7. ohnomer/servers firewall config

- [ ] 7.1 In `ohnomer/servers/hyperv/academy/install.sh`, add `sudo ufw allow 9000:9049/tcp` (or document the Tailscale ACL equivalent)

## 8. Tests

- [ ] 8.1 Unit tests: `_allocate_ui_port` returns next free port; raises on exhaustion; `_release_ui_port` frees correctly
- [ ] 8.2 Unit test: `launch` response includes `ui_url`; `crews` list includes `ui_url`; `nuke` releases port
- [ ] 8.3 Unit test: `GA_UI_PORT_ENABLED=false` skips port allocation
- [ ] 8.4 Manual smoke test on vm23: launch a crew, open `ui_url` in browser, confirm SPA loads, navigate to `/chat`, hard reload — confirm it still renders

## 9. Spec sync and validation

- [ ] 9.1 Merge delta specs into main specs: `proxy-hosting`, `crew-lifecycle`
- [ ] 9.2 Create `openspec/specs/crew-ui-spa-routing/spec.md` from the change spec
- [ ] 9.3 Run `openspec validate` and confirm no errors
