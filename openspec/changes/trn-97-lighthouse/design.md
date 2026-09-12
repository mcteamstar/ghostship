# Design: ga-lighthouse — Fleet-Level Observability (TRN-97)

## Container Specification

### Image

A new `Containerfile` at `lighthouse/Containerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
COPY static/ ./static/
EXPOSE 7474
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7474"]
```

Dependencies (`lighthouse/requirements.txt`):
```
uvicorn>=0.31.1,<1.0.0
starlette>=1.0.1,<2.0.0
httpx2==2.12.0
```

These are kept in sync with the transport's `requirements.txt` pins — use the
same versions to avoid image-layer divergence and ensure API compatibility.

### Directory Layout

```
lighthouse/
  Containerfile
  requirements.txt
  server.py          ← uvicorn/Starlette app: static serving + proxy routes
  static/
    index.html       ← single-page fleet dashboard (vanilla JS)
    style.css        ← optional extracted styles (may be inline in index.html)
```

### Secrets

The container mounts two Podman secrets:

| Secret name | File inside container | Purpose |
|:---|:---|:---|
| `ga-transport-secret` | `/run/secrets/ga-transport-secret` | `X-Transport-Token` header on all calls to `ga-transport` |
| `ga-api-key` | `/run/secrets/ga-api-key` | Bearer auth header for `GET /api/crews` and other authenticated transport endpoints. Only mounted when `GA_API_KEY` is set. |

Both follow the exact same pattern as `ga-portal`. The lighthouse server reads
them at startup:

```python
def _read_secret(path: str, default: str = "") -> str:
    try:
        return open(path).read().strip()
    except FileNotFoundError:
        return default

TRANSPORT_TOKEN = _read_secret("/run/secrets/ga-transport-secret")
API_KEY = _read_secret("/run/secrets/ga-api-key")
```

### Environment Variables

| Variable | Default | Purpose |
|:---|:---|:---|
| `TRANSPORT_URL` | `http://ga-transport:64057` | Base URL for all transport API calls |
| `GA_LIGHTHOUSE_PORT` | `7474` | Internal listen port |

The lighthouse server does not read `GA_API_KEY` from the environment directly;
it reads the secret file at runtime. This avoids the key appearing in `podman
inspect`.

---

## Compose Addition

Added to `DATA_DIR/compose.yml` when `GA_LIGHTHOUSE_ENABLED=true`. The block is
generated inline in `scripts/install.sh`, after the `ga-portal` block:

```yaml
  ga-lighthouse:
    image: localhost/lighthouse:latest
    container_name: ga-lighthouse
    restart: always
    networks:
      - ga-portside
    environment:
      TRANSPORT_URL: "http://ga-transport:64057"
      GA_LIGHTHOUSE_PORT: "7474"
    secrets:
      - ga-transport-secret
      # ga-api-key conditionally added when GA_API_KEY is set
```

Critical: `ga-starboard` is deliberately absent from `networks`. Any code
review of the generated `compose.yml` must verify this.

No host port binding. All external access goes through `ga-portal`. No persistent
volume is needed (read-only observability, no state written by lighthouse).

The image build step is added to `install.sh` after the transport build:

```bash
if [[ "${GA_LIGHTHOUSE_ENABLED:-false}" == "true" ]]; then
  podman build -t localhost/lighthouse:latest "${GHOSTSHIP_DIR}/lighthouse/"
fi
```

---

## Caddy Route

Added to `DATA_DIR/caddy/initial-config.json` inside the `ga-main` server's
`routes` array when `GA_LIGHTHOUSE_ENABLED=true`. Inserted **before** the
`ga-transport-misc` catch-all route.

### With `GA_API_KEY` set (authenticated install)

```json
{
  "@id": "ga-lighthouse",
  "match": [{"path": ["/lighthouse", "/lighthouse/*"]}],
  "handle": [
    {
      "handler": "reverse_proxy",
      "upstreams": [{"dial": "ga-transport:64057"}],
      "rewrite": {"method": "GET", "uri": "/dashboard/auth"},
      "headers": {
        "request": {
          "set": {
            "X-Forwarded-Method": ["{http.request.method}"],
            "X-Forwarded-Uri": ["{http.request.uri}"],
            "X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"]
          }
        }
      },
      "handle_response": [
        {
          "match": {"status_code": [2]},
          "routes": [{"handle": [{"handler": "vars"}]}]
        }
      ]
    },
    {
      "handler": "rewrite",
      "uri_substring": [{"find": "/lighthouse", "replace": ""}]
    },
    {
      "handler": "reverse_proxy",
      "upstreams": [{"dial": "ga-lighthouse:7474"}],
      "headers": {
        "request": {
          "set": {
            "X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"]
          }
        }
      }
    }
  ]
}
```

### Without `GA_API_KEY` (open install, e.g. Tailscale-gated)

Same block but with the `forward_auth` handler omitted:

```json
{
  "@id": "ga-lighthouse",
  "match": [{"path": ["/lighthouse", "/lighthouse/*"]}],
  "handle": [
    {
      "handler": "rewrite",
      "uri_substring": [{"find": "/lighthouse", "replace": ""}]
    },
    {
      "handler": "reverse_proxy",
      "upstreams": [{"dial": "ga-lighthouse:7474"}]
    }
  ]
}
```

The `/lighthouse` prefix is stripped before forwarding, so the lighthouse
server sees `/` for the SPA root and `/api/*` for its API. The `/lighthouse`
(no trailing slash) match ensures the redirect case is handled — Caddy itself
does not append the trailing slash, so both patterns are matched.

### Route Ordering

The lighthouse route is inserted **before** `ga-transport-misc` (the existing
catch-all for `/health`, `/version`, `/dashboard/*`, `/login`, `/logout`).
Order matters in Caddy — a more specific path match earlier in the array
wins. Since `/lighthouse/*` is disjoint from all existing routes, the
insertion position only needs to be before any potential catch-all. Currently
there is no catch-all; inserting before `ga-transport-misc` is the safe
convention.

---

## Transport API Additions

Two new authenticated REST endpoints on `ga-transport` (`transport/server.py`).
Both require Bearer auth when `GA_API_KEY` is set (same as all existing
authenticated endpoints via `BearerAuthMiddleware`).

### `GET /api/crews`

Returns the fleet registry augmented with live agent state. Shape mirrors the
`crews()` MCP tool exactly so consumers can use either path.

**Response** (`200 OK`, `application/json`):

```json
{
  "crews": [
    {
      "crew_id": "general",
      "container": "gs-general",
      "status": "active",
      "composition": "spec-ops",
      "created_at": "2026-09-01T10:00:00Z",
      "last_task_at": "2026-09-12T12:55:00Z",
      "gateway_healthy": true,
      "crew_image_version": "0.5.0",
      "uptime_secs": 3600,
      "dashboard_url": "http://localhost:64058",
      "agents": [
        {"task_id": "abc123", "agent": "ghost", "done": false, "elapsed_secs": 120}
      ],
      "host_memory_available_gb": 8.4,
      "active_crews": 2,
      "max_active_crews": 3
    }
  ]
}
```

**Implementation note**: This endpoint calls `_load_registry()` (already
used by `crews()`) and performs the same gateway health-probe logic. It does
not call the MCP session machinery — it is a direct Python call into the
registry and podman layers, wrapped in a Starlette route handler.

The endpoint is added under an `/api/` path prefix to distinguish REST-JSON
routes from the existing MCP and proxy routes. This prefix does not exist
today; the new routes establish it. No existing routes use `/api/`.

### `GET /api/crews/{crew_id}/mail`

Returns mail counts and recent subjects for all persona mailboxes within a
given crew container. Reuses the `_skim_all_mailboxes()` function already in
`transport/captain.py` via a container exec call.

**Response** (`200 OK`, `application/json`):

```json
{
  "crew_id": "general",
  "mailboxes": {
    "ghost":   {"unread": 2, "subjects": ["TRN-97 plan ready", "lighthouse discovery attached"]},
    "spectre": {"unread": 0, "subjects": []},
    "banshee": {"unread": 0, "subjects": []},
    "wraith":  {"unread": 1, "subjects": ["re: discovery report"]},
    "reaper":  {"unread": 0, "subjects": []},
    "raven":   {"unread": 0, "subjects": []},
    "captain": {"unread": 0, "subjects": []},
    "admiral": {"unread": 0, "subjects": []}
  }
}
```

**404** when `crew_id` is not in the registry. **503** when the crew
container is not running (exec call fails).

**Implementation note**: The `_skim_all_mailboxes()` function is called via
container exec today. The new endpoint calls the same internal function but
wraps the result in a JSON response. The exec-based path is unchanged;
the endpoint is a thin HTTP wrapper.

### Auth Pattern

Both endpoints are registered in `server.py` after the existing routes. They
are gated by `BearerAuthMiddleware` when `GA_API_KEY` is set — same as
`/mcp*`, `/files/*`, etc. No new auth machinery is needed.

---

## SPA Design (Vanilla JS, No Build Step)

### What it shows

The SPA renders a fleet dashboard with three zones:

**Fleet header bar** (top):
- Ghostship version (`GET /version` — public, no auth)
- Host memory available (from `GET /api/crews`)
- Active crews / max active crews ratio
- Last-updated timestamp

**Crew cards** (main grid, one per crew):
- Crew ID, status badge (`active` / `idle` / `starting`)
- Running tasks: task ID prefix, agent name, elapsed time
- Uptime in human-readable form (`2h 15m`)
- Mail badge: total unread across all personas (click to expand)
- Mail panel (expanded on click): per-persona unread count + latest subjects
- "Open dashboard" link — navigates to `window.location.origin + '/crews/' + crew_id + '/ui/'`
  which routes through `ga-portal → ga-transport → crew gateway`

**Empty state**: "No crews found" card with a note to run `launch`.

### Polling

```javascript
const POLL_INTERVAL = 3000; // ms

async function fetchFleet() {
  const res = await fetch('/api/crews', {
    headers: { 'Authorization': `Bearer ${API_KEY}` }
  });
  if (!res.ok) return;
  return res.json();
}

function startPolling() {
  fetchFleet().then(render);
  setInterval(() => fetchFleet().then(render), POLL_INTERVAL);
}
```

The API key is injected into the HTML at serve time by the lighthouse server
(a template variable), so the SPA does not need a login UI. If `GA_API_KEY`
is not set, the Bearer header is omitted and the transport accepts the request
directly (same open-mode behaviour as the portal today).

Mail data is fetched per crew, on-demand (when the mail badge is clicked),
via `GET /api/crews/{crew_id}/mail`. It is not polled — it is fetched once
per click and cached for 10 s.

### "Open Dashboard" Link Behaviour

The link opens the crew's dashboard via `ga-portal`:

```
https://<portal-host>/crews/{crew_id}/ui/
```

This is a standard navigation — not proxied by the lighthouse server. The
browser sends the request to `ga-portal`, which routes it through the
transport's `/crews/{crew_id}/ui/*` reverse proxy (with cookie injection) and
delivers the crew SPA. Lighthouse does not proxy this request; it only
renders the link. This is intentional: adding a proxy chain through lighthouse
for dashboard traffic would create a three-hop path with no benefit over the
existing two-hop one.

### Auth in the SPA

When `GA_API_KEY` is set, the Caddy route gates `/lighthouse/*` via
`forward_auth` against `/dashboard/auth`. This means the user must have a
valid `gs_session` cookie (obtained via `/dashboard/login`) before Caddy
allows any request to reach lighthouse. The SPA itself does not handle login
— it relies entirely on the portal's `forward_auth` gate. If the cookie
expires, Caddy redirects the browser to `/dashboard/login` (same as per-crew
dashboards today).

---

## Auth Approach Summary

| Mode | How lighthouse is protected |
|:---|:---|
| No `GA_API_KEY` | No portal gate; security relies on network (Tailscale, VPN, localhost) |
| `GA_API_KEY` set | Caddy `forward_auth` gate on `/lighthouse/*` using `gs_session` cookie; lighthouse calls transport with Bearer token from the mounted `ga-api-key` secret |

This reuses all existing auth infrastructure — no new tokens, no new login
flows.

---

## `install.sh` Changes

### New config variable

```bash
GA_LIGHTHOUSE_ENABLED=false
```

Added to the defaults block (same location as `GA_DASHBOARD_DEFAULT`,
`GA_PREWARM_ENABLED`). Readable from the config file or `--lighthouse` flag.

### Image build (after transport build)

```bash
if [[ "${GA_LIGHTHOUSE_ENABLED:-false}" == "true" ]]; then
  echo "Building ga-lighthouse image..."
  podman build -t localhost/lighthouse:latest "${GHOSTSHIP_DIR}/lighthouse/"
  echo "✓ ga-lighthouse image built"
fi
```

### Compose block (inside the heredoc, after ga-portal block)

```bash
$(if [[ "${GA_LIGHTHOUSE_ENABLED:-false}" == "true" ]]; then cat <<LHEOF
  ga-lighthouse:
    image: localhost/lighthouse:latest
    container_name: ga-lighthouse
    restart: always
    networks:
      - ga-portside
    environment:
      TRANSPORT_URL: "http://ga-transport:64057"
      GA_LIGHTHOUSE_PORT: "7474"
    secrets:
      - ga-transport-secret
$(if [[ -n "${GA_API_KEY:-}" ]]; then printf '      - ga-api-key\n'; fi)
LHEOF
fi)
```

### Caddy route (inside the initial-config.json generation block)

The lighthouse route JSON fragment is generated into a shell variable
`_LIGHTHOUSE_ROUTE` (empty string when disabled), then interpolated into the
routes array before `ga-transport-misc`.

### `start.sh` / `uninstall.sh`

`start.sh` uses the generated `compose.yml` — no changes needed (lighthouse
is or is not present in the file). `uninstall.sh` adds `ga-lighthouse` to
its container removal list, gated on the same `GA_LIGHTHOUSE_ENABLED` flag
read from the config file.

---

## `config.py` Addition

```python
# ── Fleet observability (TRN-97) ─────────────────────────────────────────────
ga_lighthouse_enabled: bool = False
```

Added to the `Config` dataclass. The transport reads this flag to
conditionally register the `/api/crews` and `/api/crews/{id}/mail` routes
at startup. When disabled, the routes simply do not exist.

```python
# in Config.from_env():
ga_lighthouse_enabled=_env_bool_default_off("GA_LIGHTHOUSE_ENABLED"),
```

When `GA_LIGHTHOUSE_ENABLED=false` (the default), the `/api/` routes are not
registered. This means the lighthouse container cannot accidentally call them
and receive a useful response if it is somehow started without the flag.

---

## Testing Strategy

Three new test files (no code in this plan — locations only):

- `tests/unit/test_lighthouse_routes.py` — unit tests for the two new
  transport endpoints using the existing `TestClient` / stub pattern from
  `tests/unit/_stubs.py`.
- `tests/unit/test_lighthouse_config.py` — tests for `GA_LIGHTHOUSE_ENABLED`
  config parsing.
- `tests/integration/test_install_lighthouse.sh` — integration test that runs
  `install.sh` with `GA_LIGHTHOUSE_ENABLED=true` and verifies the lighthouse
  service block appears in `compose.yml` and the Caddy route appears in
  `initial-config.json`.

Existing test files (`test_server.py`, `test_caddy.py`) need additions to
cover the new routes and the config flag.

---

## Open Questions (resolved in design)

| Question | Decision |
|:---|:---|
| Path prefix vs subdomain | Path prefix (`/lighthouse/*`) — avoids DNS/TLS complexity |
| SPA framework | Vanilla JS — no build step, no npm, consistent with transport's philosophy |
| Auth approach | Reuse `forward_auth` + `gs_session` cookie; no new tokens |
| Data freshness | 3-second poll for crew cards; on-demand for mail |
| Crew dashboard access | Link only (navigates via portal); lighthouse does not proxy dashboard WS |
| Log tailing | Out of scope for MVP |
| SSE / WebSocket push | Out of scope; deferred to follow-on TRN |
