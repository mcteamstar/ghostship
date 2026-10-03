# TRN-191 Tasks

## 1. Fix `_patch_crew_config` in `transport/lifecycle.py`

- [ ] 1.1 Confirm `CREW_CONTAINER_PREFIX` and `CREW_GATEWAY_PORT` are reachable
  in `lifecycle.py` (module-level constants in `server.py`); import them or
  pass the composed value in rather than re-declaring literals
- [ ] 1.2 In `_patch_crew_config`, add `dashboard.url` to the config patch dict:
  ```python
  "dashboard": {"url": f"http://{CREW_CONTAINER_PREFIX}{crew_id}:{CREW_GATEWAY_PORT}"}
  ```
- [ ] 1.3 Verify deep-merge precedence: confirm `config.local.json` overrides
  `config.json` (local-over-base), so unconditionally setting `dashboard.url`
  here is correct and no "only if unset" guard is needed

## 2. Update dashboard-proxy spec

- [ ] 2.1 Ensure the delta at
  `openspec/changes/trn-191-ws-dashboard-url-origin/specs/transport/dashboard-proxy/spec.md`
  documents the new requirement: patched `config.local.json` carries
  `dashboard.url`; the gateway's `allowed_origins` includes
  `http://gs-{crew_id}:5476`; the proxied WS `Origin` is accepted (101); the
  external-origin exclusion still holds

## 3. Tests

- [ ] 3.1 Add a unit test asserting `_patch_crew_config` output includes
  `dashboard.url` == `http://gs-{crew_id}:5476` (exact string match)
- [ ] 3.2 Run the full unit test suite and confirm it passes

## 4. Deploy and validate

- [ ] 4.1 Deploy the updated transport to academy
- [ ] 4.2 Launch a new crew with `dashboard=True`
- [ ] 4.3 Open the dashboard in a browser; confirm WS connects — devtools shows
  `101 Switching Protocols` on `ws://host:port/api/ws` (not 403)
- [ ] 4.4 Confirm the sessions list loads and live updates work
- [ ] 4.5 Confirm the import modal can be dismissed normally
