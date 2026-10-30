## 1. Transport — Shared fleet data helper

- [x] 1.1 In `transport/tools.py`, extract the crew list assembly from `_tools_crews`
  into a new module-level function `_build_crews_payload(podman)` that returns the
  full dict (crews list + host_memory_available_gb + active_crews + max_active_crews).
  Update `_tools_crews` to call it.
- [x] 1.2 Write unit tests for `_build_crews_payload` in `tests/unit/test_tools.py`
  (or a new `test_fleet.py`) using `FakePodmanClient` — cover empty fleet, running
  crew, stopped crew, crew with dashboard_url.

## 2. Transport — `GET /api/crews` REST endpoint

- [x] 2.1 Add `async def _handle_api_crews_get(request)` handler in `transport/server.py`
  (or `transport/fleet.py`). Call `_build_crews_payload(podman)` and return a
  `JSONResponse`.
- [x] 2.2 Register `("GET", "/api/crews")` in the `public_routes` dict of
  `BearerAuthMiddleware` in `server.py`'s `__main__` block (session enforcement is
  at the Caddy `forward_auth` layer, same as `/crews/*/ui`).
- [x] 2.3 Register the route in `_openapi_schema_public_routes` in `server.py` so
  it appears in `/openapi.json`.
- [x] 2.4 Write unit tests for `_handle_api_crews_get` covering: 200 with fleet
  JSON, correct `Content-Type`, correct shape when fleet is empty.

## 3. Transport — `GET /` Lighthouse SPA handler

- [x] 3.1 Write the Lighthouse HTML string. The SPA must:
  - Fetch `/api/crews` on load and every 5 s using `fetch("/api/crews", {credentials: "include"})`
  - Render a table with columns: crew_id, status, backend, composition,
    uptime, last_task_at
  - Expand a row on click to fetch and display `/crews/{id}/api/spawn` (tasks)
    and `/crews/{id}/api/crons` (captain/schedule state)
  - Show a link to `dashboard_url` when non-null (opens in new tab)
  - Use only vanilla JS (`fetch` + DOM) — no external CDN scripts
- [x] 3.2 Add `async def _handle_lighthouse_get(request)` handler that returns
  `HTMLResponse(LIGHTHOUSE_HTML)`.
- [x] 3.3 Register `("GET", "/")` in the `public_routes` dict of
  `BearerAuthMiddleware` (session enforcement at Caddy layer).
- [x] 3.4 Write a unit test confirming `GET /` returns HTTP 200 with
  `Content-Type: text/html` and a non-empty body.

## 4. Caddy — add `ga-lighthouse` session-gated route

- [x] 4.1 In `bin/install.sh`, add a new `ga-lighthouse` JSON route object to
  `initial-config.json` matching paths `/`, `/api/crews*`, `/crews/*/api/*` with
  the same `forward_auth` → `reverse_proxy` chain used by per-crew dashboard
  servers (calling `GET /dashboard/auth` on the transport, then proxying to
  `ga-transport:64057`).
- [x] 4.2 When `GA_API_KEY` is unset, emit the `ga-lighthouse` route without the
  `forward_auth` handler (passthrough only) — consistent with the no-key behaviour
  of `/mcp*`.

## 5. Verification

- [x] 5.1 Run the full unit test suite (`pytest tests/unit/`) — all tests pass.
- [ ] 5.2 Start a local dev transport and confirm `GET /` returns 200 HTML and
  `GET /api/crews` returns 200 JSON.
- [ ] 5.3 Confirm the Lighthouse SPA renders a fleet table when at least one crew
  is registered in `crews.json`.
- [ ] 5.4 Confirm `GET /api/crews` and the MCP `crews()` tool return the same
  crew entries (manual spot-check or a test).## Context

The transport (`transport/server.py`) is a Starlette/uvicorn app fronted by
`BearerAuthMiddleware`. Routes are registered as `(method, path)` tuples in two
dicts: `routes` (bearer-gated) and `public_routes` (open). `BearerAuthMiddleware`
dispatches matching requests to handler callables; the MCP app handles everything
else via pass-through.

Caddy (`ga-portal`) is the sole public entry point. Its `initial-config.json`
(written by `bin/install.sh`) carries a `ga-transport-misc` catch-all route that
forwards a fixed list of path prefixes to `ga-transport:64057`. Paths not in that
list are never forwarded and return 404 from Caddy. `/`, `/api/crews*`, and
`/crews/*/api/*` are currently absent from that list.

The MCP `crews()` tool assembles fleet data in `transport/tools.py`. That logic
is not reachable over HTTP today.

See `proposal.md` for motivation.
