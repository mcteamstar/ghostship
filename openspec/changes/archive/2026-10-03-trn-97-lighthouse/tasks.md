# Tasks: ga-lighthouse — Fleet-Level Observability (TRN-97)

Ordered implementation plan. Each task is a logical unit of work; dependencies
are explicit. The plan is structured in layers: transport changes first, then
the lighthouse container, then install/compose integration, then tests.

---

## Layer 1 — Transport: Config + New REST Endpoints

### Task T1: Add `ga_lighthouse_enabled` to `Config`

**File**: `transport/config.py`

Add the field to the `Config` dataclass:
```python
# ── Fleet observability (TRN-97) ─────────────────────────────────────────────
ga_lighthouse_enabled: bool = False
```

Add to `Config.from_env()`:
```python
ga_lighthouse_enabled=_env_bool_default_off("GA_LIGHTHOUSE_ENABLED"),
```

No behaviour change when the field is `false`. Verify that `Config()` with no
args still produces `ga_lighthouse_enabled=False`.

**Acceptance**: `Config()` has the new field with default `False`.
`Config.from_env()` reads `GA_LIGHTHOUSE_ENABLED` using `_env_bool_default_off`.
Existing unit tests pass unchanged.

---

### Task T2: Implement `GET /api/crews` endpoint in the transport

**File**: `transport/server.py`

Register a new Starlette route `GET /api/crews` that:

1. Checks `cfg.ga_lighthouse_enabled` — if `False`, immediately returns
   `404 Not Found`.
2. Calls `_load_registry()` (already present in `server.py`) to get the
   current crew list.
3. For each crew, invokes the same live-state probe logic used by the `crews()`
   MCP tool (gateway health check, uptime calculation, agent list from task
   state).
4. Returns a JSON response with shape `{"crews": [...]}` where each element
   matches the shape documented in `design.md` under
   "GET /api/crews response".

The route is gated by `BearerAuthMiddleware` when `GA_API_KEY` is set —
exactly the same middleware already wrapping `/mcp*` and `/files/*`.

The implementation must not duplicate the `crews()` MCP tool logic from
scratch; instead it should call the same internal helper functions (`_load_registry`,
the gateway probe, `_task_timestamps`) that the MCP tool already calls, or
extract those functions into a shared utility that both the MCP tool and this
route call.

**Acceptance**: `GET /api/crews` with a valid Bearer token returns `200` with
the correct JSON shape: top-level `crews` array plus top-level
`host_memory_available_gb`, `active_crews`, `max_active_crews` (matching the
`crews()` MCP tool response shape). With no token (when `GA_API_KEY` is set),
returns `401`. When `GA_LIGHTHOUSE_ENABLED=false`, returns `404`.

---

### Task T3: Implement `GET /api/crews/{crew_id}/mail` endpoint in the transport

**File**: `transport/server.py`

Register a new Starlette route `GET /api/crews/{crew_id}/mail` that:

1. Checks `cfg.ga_lighthouse_enabled` — if `False`, returns `404 Not Found`.
2. Looks up `crew_id` in the registry — if not found, returns `404 Not Found`.
3. Checks whether the crew container is running (via `podman.py` or the
   registry's `status` field) — if not running, returns `503 Service
   Unavailable` with a JSON body `{"error": "crew container not running"}`.
4. Calls the existing `_skim_all_mailboxes(crew_id)` function from
   `transport/captain.py` (or its equivalent exec-based path) to retrieve
   per-persona unread counts and subjects.
5. Returns a JSON response with shape:
   ```json
   {
     "crew_id": "<id>",
     "mailboxes": {
       "<persona>": {"unread": N, "subjects": ["...", "..."]}
     }
   }
   ```
   Maximum 5 subjects per persona, most recent first.

Same Bearer auth gating as T2.

**Acceptance**: Returns correct mail data for a running crew. Returns `404`
for unknown crew. Returns `503` for stopped crew. Returns `404` when
`GA_LIGHTHOUSE_ENABLED=false`.

---

## Layer 2 — Lighthouse Container

### Task T4: Create `lighthouse/` directory and `Containerfile`

**New files**:
- `lighthouse/Containerfile`
- `lighthouse/requirements.txt`

Contents as specified in `design.md` under "Container Specification". Pin all
versions. The three dependencies (`uvicorn`, `starlette`, `httpx2`) must use
the same pinned versions as `transport/requirements.txt` — use `httpx2`, not
`httpx` (the transport migrated to `httpx2` in TRN-155; `httpx` is no longer
a direct transport dependency).

Verify the image builds with `podman build -t localhost/lighthouse:latest
lighthouse/`. It must produce a runnable container.

**Acceptance**: `podman build` succeeds. `podman run --rm -e TRANSPORT_URL=http://localhost:64057
localhost/lighthouse:latest` starts without import errors (it will fail to
connect to transport, which is expected in isolation).

---

### Task T5: Implement `lighthouse/server.py`

**New file**: `lighthouse/server.py`

Starlette application that:

1. Reads `TRANSPORT_TOKEN` from `/run/secrets/ga-transport-secret` at startup.
   Reads `API_KEY` from `/run/secrets/ga-api-key` at startup (empty string if
   absent). Logs a warning if `TRANSPORT_TOKEN` is empty.
2. Serves `GET /` and `GET /static/*` — returns `index.html` and `style.css`
   from `./static/`. The API key value is injected into `index.html` as a
   template variable when it is non-empty (so the SPA can include it in fetch
   calls). **Do not inject the transport token** — that is only used server-side.
3. Implements a proxy route `GET /api/*` that:
   - Adds `X-Transport-Token: <TRANSPORT_TOKEN>` to all outbound requests
   - If `API_KEY` is non-empty, adds `Authorization: Bearer <API_KEY>`
   - Forwards to `http://ga-transport:64057/api/{rest-of-path}` via `httpx2`
     (`import httpx2 as httpx` — consistent with the transport and TRN-155)
   - Streams the response body and status code back to the browser unchanged
   - Sets a hard timeout of 10 s per request
4. Implements a `GET /healthz` endpoint that returns `200 OK {"status": "ok"}`.
   This is called by `compose.yml`'s healthcheck (see Task T7).

The proxy at step 3 allows the SPA to call `/api/crews` without embedding the
transport token in JavaScript. The SPA only needs the API key (user-facing
Bearer token); the transport token is added server-side.

No WebSocket proxying, no crew dashboard proxying — those go through the portal
directly.

**Acceptance**: `GET /healthz` returns 200. `GET /` returns the `index.html`
content. `GET /api/crews` proxies to the transport (or returns a 502 in test
when the transport is absent).

---

### Task T6: Implement `lighthouse/static/index.html`

**New file**: `lighthouse/static/index.html`

Single HTML file containing:
- A `<head>` with a `<title>Ghostship Fleet</title>`, inline or linked CSS.
- A `<body>` with a `<div id="app"></div>` mount point.
- A `<script type="module">` block that implements the polling fleet dashboard
  described in `design.md` under "SPA Design".
- No external CDN dependencies. No bundler. Pure DOM APIs.

The script must:
1. On load: call `fetchFleet()` and render; start a 3-second `setInterval`.
2. `fetchFleet()`: `GET /api/crews` (through the lighthouse proxy, so no
   token needed in JS beyond what the server injects). On error: display an
   error banner without clearing the existing crew cards.
3. `render(data)`: for each crew in `data.crews`, create or update a card in
   `#app`. Cards contain: crew ID, status badge (colour-coded), running task
   count + agent names, uptime, and a mail badge (total unread).
4. Mail badge click: `GET /api/crews/{id}/mail`, render per-persona rows.
   Cache the response for 10 s (keyed by crew ID, invalidated on next click
   after TTL).
5. "Open dashboard" link: `href = window.location.origin + '/crews/' + crewId + '/ui/'`.
6. Fleet header: show `active_crews` / `max_active_crews` and
   `host_memory_available_gb` from the top-level fields of the `/api/crews`
   response (i.e. `data.active_crews`, `data.max_active_crews`,
   `data.host_memory_available_gb` — not from inside any crew element).
7. Last-updated timestamp in the header, updated on every successful poll.

Style: minimal, functional. Dark-on-light or light-on-dark is acceptable.
Must be readable in a browser at 1280px width. No accessibility regressions
(use semantic HTML, `aria-label` on badge buttons, `role="status"` on the
last-updated indicator).

**Acceptance**: Renders crew cards from the `/api/crews` response. Mail panel
expands on badge click. No console errors in a modern browser.

---

## Layer 3 — Compose and Caddy Integration

### Task T7: Add lighthouse block to compose generation in `install.sh`

**File**: `scripts/install.sh`

Changes:

1. **Default variable**: add `GA_LIGHTHOUSE_ENABLED=false` to the defaults block
   (near `GA_DASHBOARD_DEFAULT` and `GA_PREWARM_ENABLED`).

2. **Image build**: after the transport image build block, add:
   ```bash
   if [[ "${GA_LIGHTHOUSE_ENABLED:-false}" == "true" ]]; then
     echo "Building ga-lighthouse image..."
     podman build -t localhost/lighthouse:latest "${GHOSTSHIP_DIR}/lighthouse/"
     echo "✓ ga-lighthouse image built"
   fi
   ```

3. **Compose block**: inside the `compose.yml` heredoc, after the `ga-portal`
   service and before the `networks:` section, add:
   ```bash
   $(if [[ "${GA_LIGHTHOUSE_ENABLED:-false}" == "true" ]]; then
     printf '  ga-lighthouse:\n'
     printf '    image: localhost/lighthouse:latest\n'
     printf '    container_name: ga-lighthouse\n'
     printf '    restart: always\n'
     printf '    networks:\n'
     printf '      - ga-portside\n'
     printf '    environment:\n'
     printf '      TRANSPORT_URL: "http://ga-transport:64057"\n'
     printf '      GA_LIGHTHOUSE_PORT: "7474"\n'
     printf '    secrets:\n'
     printf '      - ga-transport-secret\n'
     if [[ -n "${GA_API_KEY:-}" ]]; then
       printf '      - ga-api-key\n'
     fi
     printf '    healthcheck:\n'
     printf '      test: ["CMD", "curl", "-f", "http://localhost:7474/healthz"]\n'
     printf '      interval: 30s\n'
     printf '      retries: 3\n'
   fi)
   ```

4. **Container cleanup before compose up**: add `ga-lighthouse` to the
   `podman rm -f` calls (alongside `ga-transport` and `ga-portal`) so a
   reinstall over an existing deployment tears down the old lighthouse
   container cleanly.

**Acceptance**: Running `install.sh` with `GA_LIGHTHOUSE_ENABLED=true` produces
a `compose.yml` containing the `ga-lighthouse` service with only `ga-portside`
in its networks. Running without the flag produces no lighthouse block.

---

### Task T8: Add lighthouse Caddy route to `initial-config.json` generation

**File**: `scripts/install.sh`

In the `initial-config.json` generation section (after the `_AUTH_ROUTES`
variable is built and before the final `cat > ... <<CADDY_EOF` heredoc):

1. Build a `_LIGHTHOUSE_ROUTE` shell variable:
   ```bash
   if [[ "${GA_LIGHTHOUSE_ENABLED:-false}" == "true" ]]; then
     if [[ -n "${GA_API_KEY:-}" ]]; then
       _LIGHTHOUSE_ROUTE=$(cat <<LHEOF
               {
                 "@id": "ga-lighthouse",
                 "match": [{"path": ["/lighthouse", "/lighthouse/*"]}],
                 "handle": [
                   {
                     "handler": "reverse_proxy",
                     "upstreams": [{"dial": "ga-transport:64057"}],
                     "rewrite": {"method": "GET", "uri": "/dashboard/auth"},
                     "headers": {"request": {"set": {
                       "X-Forwarded-Method": ["{http.request.method}"],
                       "X-Forwarded-Uri": ["{http.request.uri}"],
                       "X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"]
                     }}},
                     "handle_response": [{"match": {"status_code": [2]}, "routes": [{"handle": [{"handler": "vars"}]}]}]
                   },
                   {"handler": "rewrite", "uri_substring": [{"find": "/lighthouse", "replace": ""}]},
                   {"handler": "reverse_proxy", "upstreams": [{"dial": "ga-lighthouse:7474"}],
                    "headers": {"request": {"set": {"X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"]}}}}
                 ]
               },
   LHEOF
   )
     else
       _LIGHTHOUSE_ROUTE=$(cat <<LHEOF
               {
                 "@id": "ga-lighthouse",
                 "match": [{"path": ["/lighthouse", "/lighthouse/*"]}],
                 "handle": [
                   {"handler": "rewrite", "uri_substring": [{"find": "/lighthouse", "replace": ""}]},
                   {"handler": "reverse_proxy", "upstreams": [{"dial": "ga-lighthouse:7474"}]}
                 ]
               },
   LHEOF
   )
     fi
   else
     _LIGHTHOUSE_ROUTE=""
   fi
   ```

2. In the `CADDY_EOF` heredoc, interpolate `${_LIGHTHOUSE_ROUTE}` as a line
   **before** the `ga-transport-misc` route object.

**Acceptance**: With `GA_LIGHTHOUSE_ENABLED=true`, `initial-config.json`
contains the `ga-lighthouse` route. With the flag off, it is absent. The JSON
is valid (use `python3 -m json.tool` or `jq .` to verify).

---

### Task T9: Update `scripts/uninstall.sh` for lighthouse

**File**: `scripts/uninstall.sh`

Add `ga-lighthouse` to the container removal steps, gated on the same
`GA_LIGHTHOUSE_ENABLED` config variable detection the script already uses for
other optional components.

Check the uninstall script's existing pattern for how it determines which
containers to stop/remove and replicate it for lighthouse.

**Acceptance**: `uninstall.sh` with `GA_LIGHTHOUSE_ENABLED=true` config stops
and removes the `ga-lighthouse` container. Without the flag, it is a no-op for
lighthouse.

---

## Layer 4 — Configuration Documentation

### Task T10: Document `GA_LIGHTHOUSE_ENABLED` in `docs/configuration.md`

**File**: `docs/configuration.md`

Add an entry for `GA_LIGHTHOUSE_ENABLED` in the appropriate section
(alongside the other optional feature flags like `GA_PREWARM_ENABLED` and
`GA_DASHBOARD_DEFAULT`). The entry must include:

- Description: what lighthouse is and what enabling this flag does
- Default: `false`
- Accepted values: `true` / `false`
- Side effects: requires the lighthouse image to be built (handled by
  `install.sh` automatically)
- Note: also controls whether the transport registers the `/api/crews` and
  `/api/crews/{id}/mail` REST endpoints

**Acceptance**: The variable appears in `docs/configuration.md` in the correct
section. An operator reading the docs can understand what the flag does without
reading the source.

---

## Layer 5 — Tests

### Task T11: Unit tests for `GET /api/crews` and `GET /api/crews/{crew_id}/mail`

**New file**: `tests/unit/test_lighthouse_routes.py`

Using the existing `TestClient` + stub pattern from `tests/unit/_stubs.py`:

- Test `GET /api/crews` returns 200 with correct shape when
  `GA_LIGHTHOUSE_ENABLED=true` and registry is non-empty.
- Test `GET /api/crews` returns 404 when `GA_LIGHTHOUSE_ENABLED=false`.
- Test `GET /api/crews` returns 401 when auth is required and no token
  is supplied.
- Test `GET /api/crews/{crew_id}/mail` returns 200 with correct shape
  for a known, running crew.
- Test `GET /api/crews/{crew_id}/mail` returns 404 for an unknown crew.
- Test `GET /api/crews/{crew_id}/mail` returns 503 for a stopped crew.
- Test `GET /api/crews/{crew_id}/mail` returns 404 when
  `GA_LIGHTHOUSE_ENABLED=false`.

Also add a test to `tests/unit/test_lighthouse_config.py` (new file):
- `Config()` default: `ga_lighthouse_enabled=False`.
- `Config.from_env()` with `GA_LIGHTHOUSE_ENABLED=true`: `ga_lighthouse_enabled=True`.
- `Config.from_env()` with `GA_LIGHTHOUSE_ENABLED=0`: `ga_lighthouse_enabled=False`.

**Acceptance**: All new tests pass. `pytest tests/unit/test_lighthouse_routes.py
tests/unit/test_lighthouse_config.py` exits 0.

---

### Task T12: Integration test for `install.sh` lighthouse flag

**New file**: `tests/integration/test_install_lighthouse.sh`

Integration test that:

1. Runs `install.sh` in a dry-run / output-only mode (if supported by the
   test harness) with `GA_LIGHTHOUSE_ENABLED=true` and verifies `compose.yml`
   contains the lighthouse block with only `ga-portside` in networks.
2. Verifies `initial-config.json` contains a `ga-lighthouse` route.
3. Verifies the JSON of `initial-config.json` is valid.
4. Runs with `GA_LIGHTHOUSE_ENABLED=false` (default) and verifies neither
   file contains any lighthouse block.

Follow the pattern established by
`tests/integration/test_install_config.sh`.

**Acceptance**: The test script exits 0 for both enabled and disabled cases.
`tests/run.sh` includes the new test in its integration suite.

---

## Dependency Graph

```
T1 (config)
  └── T2 (GET /api/crews)
        └── T11 (unit tests)
  └── T3 (GET /api/crews/{id}/mail)
        └── T11 (unit tests)

T4 (Containerfile)
  └── T5 (server.py)
        └── T6 (index.html)

T7 (compose) ──┐
T8 (Caddy)  ───┤── T12 (integration test)
T9 (uninstall) ┘

T10 (docs) — independent, can be done in any order
```

T2 and T3 can be implemented in parallel. T5 can start as soon as T4 is done.
T7, T8, T9 can be done in parallel. T11 requires T2 and T3. T12 requires T7
and T8. All tests (T11, T12) are the last layer.

---

## Total: 12 tasks across 5 layers

| Layer | Tasks | Description |
|:---|:---|:---|
| 1 | T1–T3 | Transport config + REST endpoints |
| 2 | T4–T6 | Lighthouse container (Containerfile, server, SPA) |
| 3 | T7–T9 | Compose + Caddy + uninstall integration |
| 4 | T10 | Documentation |
| 5 | T11–T12 | Tests |
