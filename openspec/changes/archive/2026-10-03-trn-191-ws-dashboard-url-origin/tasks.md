# TRN-191 Tasks

## 1. Fix WS dispatch in `transport/auth.py`

- [x] 1.1 `BearerAuthMiddleware.__call__`: look up WS handler in `_public_routes`
  first, falling back to `_routes` — the handler is registered in public_routes
  (Caddy's gs_session is the gate, not bearer)
- [x] 1.2 Add unit test asserting WS handler from `public_routes` is invoked
  (not downstream): `test_ws_crew_ui_dispatches_from_public_routes`

## 2. Fix upstream WS Origin header in `transport/server.py`

- [x] 2.1 Change `crew_origin` from `http://gs-{crew_id}:5476` to
  `http://localhost:{CREW_GATEWAY_PORT}` — always in the gateway's
  `allowed_origins` regardless of config

## 3. Revert ineffective v1 approach

- [x] 3.1 Remove `dashboard.url` from `_patch_crew_config` in `lifecycle.py`
  (KiroCrew ignores it without token auth middleware active)
- [x] 3.2 Remove stale `test_trn191_dashboard_url_origin.py` test file

## 4. Update specs

- [x] 4.1 Update `openspec/specs/transport/dashboard-proxy/spec.md` WS scenario
  to document the correct Origin value and dispatch path

## 5. Deploy and validate

- [x] 5.1 Deploy to academy
- [x] 5.2 Launch authenticated crew with dashboard=True
- [x] 5.3 Browser confirms 101 on ws://{host}:{port}/api/ws, sessions list loads
