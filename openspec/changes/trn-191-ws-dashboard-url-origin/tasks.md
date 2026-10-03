# TRN-191 Tasks

## 1. Fix `_patch_crew_config` in `transport/lifecycle.py`

- [ ] 1.1 Locate the config patch dict in `_patch_crew_config` and add:
  ```python
  "dashboard": {"url": f"http://{CREW_CONTAINER_PREFIX}{crew_id}:{CREW_GATEWAY_PORT}"}
  ```
- [ ] 1.2 Confirm `CREW_CONTAINER_PREFIX` and `CREW_GATEWAY_PORT` are accessible
  in that function (they are module-level constants in `server.py`; check if
  `lifecycle.py` already imports or defines them, or pass the value in)
- [ ] 1.3 Verify the deep-merge behaviour: `config.local.json` must not
  overwrite `dashboard.url` if one already exists — confirm KiroCrew's
  deep-merge semantics (local overrides base, so setting it here is correct)

## 2. Update dashboard-proxy spec

- [ ] 2.1 Add/update scenario in
  `openspec/specs/transport/dashboard-proxy/spec.md`:
  - **WHEN** a crew is launched
  - **THEN** `config.local.json` contains `dashboard.url` set to
    `http://gs-{crew_id}:5476`
  - **THEN** the gateway's `allowed_origins` includes that origin
  - **THEN** the transport's WS proxy `Origin` header is accepted (101)

## 3. Tests

- [ ] 3.1 Add unit test asserting `_patch_crew_config` output includes
  `dashboard.url` = `http://gs-{crew_id}:5476`
- [ ] 3.2 Run full unit test suite and confirm pass

## 4. Deploy and validate

- [ ] 4.1 Deploy updated transport to academy
- [ ] 4.2 Launch a new crew with `dashboard=True`
- [ ] 4.3 Open dashboard in browser — confirm WS connects (browser devtools
  shows 101 Switching Protocols on `ws://host:port/api/ws`)
- [ ] 4.4 Confirm sessions list loads and live updates work
- [ ] 4.5 Confirm import modal can be dismissed normally
