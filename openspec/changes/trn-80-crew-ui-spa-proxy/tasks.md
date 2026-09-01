## 1. ohnomer/servers Caddy config changes

- [ ] 1.1 In `ohnomer/servers/hyperv/academy/install.sh`, change the Caddy global block from `admin off` to `admin localhost:2019`
- [ ] 1.2 In `ohnomer/servers/hyperv/academy/caddy.container`, remove `:ro` from the Caddyfile volume mount so the config dir is writable
- [ ] 1.3 Deploy to vm23 and confirm Caddy admin API is reachable: `curl -s http://localhost:2019/config/ | python3 -m json.tool`

## 2. Transport config and Caddy client

- [ ] 2.1 Add `GA_CADDY_ADMIN_URL` (default `http://localhost:2019`) and `GA_CADDY_UI_ENABLED` (default `true`) to `transport/config.py`
- [ ] 2.2 Add `scripts/install.sh` env var block entries for `GA_CADDY_ADMIN_URL` and `GA_CADDY_UI_ENABLED`
- [ ] 2.3 Write `_caddy_register_crew_ui(crew_id)` and `_caddy_remove_crew_ui(crew_id)` functions in `transport/server.py` — register via `POST http://<caddy_admin>/id/crew-ui-{crew_id}` with the route JSON; remove via `DELETE http://<caddy_admin>/id/crew-ui-{crew_id}`; log warnings on failure, never raise
- [ ] 2.4 Write the Caddy route JSON fragment: `@id: crew-ui-{id}`, `handle_path /crews/{id}/ui/*` → `reverse_proxy gs-{id}:5476`; include WebSocket passthrough headers (`Connection`, `Upgrade`)

## 3. Route persistence and startup reconciliation

- [ ] 3.1 At `_caddy_register_crew_ui`, write the route JSON to `<data_dir>/caddy_routes/<crew_id>.json`
- [ ] 3.2 At `_caddy_remove_crew_ui`, delete the route file
- [ ] 3.3 On transport startup, read all files in `caddy_routes/`; re-register routes for crews present in the registry; remove routes and files for crews not in the registry

## 4. Wire into launch and nuke

- [ ] 4.1 In `launch`, after the container is started and policy injected, call `_caddy_register_crew_ui(crew_id)` when `GA_CADDY_UI_ENABLED=true`
- [ ] 4.2 In `nuke` (confirm=True path), call `_caddy_remove_crew_ui(crew_id)` when `GA_CADDY_UI_ENABLED=true`
- [ ] 4.3 When `GA_CADDY_UI_ENABLED=false`, skip Caddy calls entirely (existing Python proxy remains)

## 5. CORS origin injection (carried over from phase 1)

- [ ] 5.1 In `transport/server.py` `container_create` env block, derive the transport's public origin from `GA_HOST_URL` (scheme+host only, strip trailing slash) or fall back to `http://localhost:{PORT}`
- [ ] 5.2 Append the public origin to `KIROCREW_CORS_ORIGINS`, comma-separated, preserving any existing value
- [ ] 5.3 Add unit tests: CORS origin injected correctly when `GA_HOST_URL` is set; when unset; when a pre-existing value is present

## 6. Tests

- [ ] 6.1 Unit tests: `_caddy_register_crew_ui` calls admin API with correct route JSON; `_caddy_remove_crew_ui` removes it; both log warnings and return on API failure
- [ ] 6.2 Unit test: startup reconciliation re-registers live routes and removes stale ones
- [ ] 6.3 Unit test: `GA_CADDY_UI_ENABLED=false` skips all Caddy calls
- [ ] 6.4 Manual smoke test on vm23: launch a crew, load `/crews/{id}/ui/` in a browser, confirm SPA navigates to `/chat` and still renders

## 7. Spec sync and validation

- [ ] 7.1 Merge delta specs into main specs: `proxy-hosting`, `crew-lifecycle`
- [ ] 7.2 Create `openspec/specs/crew-ui-spa-routing/spec.md` from the change spec
- [ ] 7.3 Run `openspec validate` and confirm no errors
