## Context

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

## Goals / Non-Goals

**Goals:**
- `GET /` returns the Lighthouse SPA HTML via the transport
- `GET /api/crews` returns fleet JSON, sharing assembly logic with the MCP tool
- Caddy forwards `/`, `/api/crews*`, `/crews/*/api/*` to the transport
- No new auth mechanism — bearer token at Caddy is the sole gate
- No new container, no new Compose service, no new Python dependency

**Non-Goals:**
- Write actions from the UI (dispatch, steer, nuke)
- SSE or WebSocket push; polling only in this version
- Log aggregation or structured event stream
- Replacing or modifying the per-crew KC dashboard

## Decisions

### D1: SPA delivered as an inline HTML string in the route handler

**Decision:** The Lighthouse HTML is a Python string literal inside a handler
function in `transport/server.py` (or a new `transport/lighthouse.py`), returned as
an `HTMLResponse`. No static file, no `StaticFiles` mount, no build step.

**Rationale:** Matches the pattern already used by `_handle_login_get` in
`transport/dashboard.py`. Zero additional files, no path assumptions, always
co-located with the handler. The SPA is intentionally minimal (fleet table + fetch
calls) — a file mount would be over-engineering for its size.

**Alternative considered:** `StaticFiles` mount serving a file from the repo.
Rejected: introduces a path assumption, makes it easy to accidentally omit the file
from the container image, and offers no real benefit for a single small HTML file.

### D2: `GET /api/crews` extracts shared assembly logic from the MCP tool

**Decision:** Extract the fleet data assembly from the MCP `crews()` tool in
`transport/tools.py` into a module-level helper (e.g. `_build_crews_payload()`).
Both the MCP tool and the new REST handler call this helper. The REST handler is
registered in `BearerAuthMiddleware` as `("GET", "/api/crews")`.

**Rationale:** The spec requires both surfaces to return identical data. A shared
helper is the only way to guarantee that without duplication. The extraction is
minimal — the function already exists, it just needs a name and to be called from
two places.

**Alternative considered:** Duplicate the assembly logic in the REST handler.
Rejected: two sources of truth will diverge.

### D3: Lighthouse is session-gated via `DashboardGate`, not bearer-gated

**Decision:** `/`, `/api/crews`, and `/crews/*/api/*` are protected by the existing
`DashboardGate` session mechanism — the same `gs_session` cookie that gates the
per-crew KC dashboard proxy (`/crews/*/ui`). Unauthenticated requests to `/` are
redirected to `/dashboard/login?next=/`. The operator logs in once; the browser
carries the `gs_session` cookie automatically on all subsequent `fetch()` calls from
the SPA. No bearer token management in JavaScript required.

In `BearerAuthMiddleware`, `/` (and the API paths called by the SPA) are listed in
`public_routes` — Caddy's `forward_auth` handler is the session gate, exactly as it
is for `/crews/*/ui`.

**Rationale:** The `DashboardGate` login flow already exists and vends a session
cookie. Reusing it for Lighthouse gives the operator a single, consistent auth UX:
open the portal, log in once, see the fleet. Bearer token management in the browser
(localStorage, URL params, etc.) would be a poor UX and a security regression.

**Alternative considered:** Bearer-gate `/` and `/api/crews` in
`BearerAuthMiddleware` (same as `/mcp`). Rejected: browsers don't forward bearer
tokens automatically on `fetch()` — the operator would need to inject the key into
JS, which is awkward and insecure.

### D4: Lighthouse paths use `forward_auth` + `reverse_proxy` in Caddy

**Decision:** `/`, `/api/crews*`, and `/crews/*/api/*` are added to the main-port
Caddy config as a new named route (`@id: "ga-lighthouse"`) using the same
`forward_auth` → `reverse_proxy` chain as the per-crew dashboard port servers.
`forward_auth` calls `GET /dashboard/auth` on the transport to validate the
`gs_session` cookie; on success Caddy proxies to `ga-transport:64057`. This is a
static config change in `bin/install.sh`'s `initial-config.json` heredoc — no Caddy
admin API call at runtime is needed.

**Rationale:** The `forward_auth` pattern is already proven for the per-crew
dashboards. Reusing it for Lighthouse ensures consistent session enforcement at the
Caddy layer. A simple passthrough (as used by `ga-transport-misc`) would bypass
session validation and expose the fleet to anyone who can reach the portal without
a `gs_session`.

**Alternative considered:** Add paths to the existing `ga-transport-misc`
passthrough route. Rejected: `ga-transport-misc` is for routes whose auth is
handled entirely by the transport (login, health, version, openapi). Lighthouse
needs the Caddy-layer `forward_auth` gate to enforce the session cookie.

### D5: Vanilla JS, no external dependencies

**Decision:** The Lighthouse SPA uses only `fetch()` and direct DOM manipulation.
No CDN-hosted libraries, no build step.

**Rationale:** No network dependency at runtime (important for airgapped/Tailscale
deployments), no build toolchain to maintain, no CSP complications from external
script sources.

**Alternative considered:** htmx or Alpine.js via CDN. Rejected: external network
dependency is unacceptable for an embedded tool dashboard.

## Risks / Trade-offs

- **SPA as a Python string is hard to edit** → Mitigation: keep it small and
  well-commented; introduce a file if it grows beyond ~200 lines.
- **`/crews/*/api/*` now publicly reachable via the portal (bearer-gated)** →
  Acceptable: it's already bearer-gated at Caddy and the transport's own
  `BearerAuthMiddleware` provides defence in depth. The crew API proxy was only
  "internal" because Caddy didn't forward it — not because it was secured beyond
  the bearer token.
- **Shared `_build_crews_payload()` helper becomes a maintenance coupling point** →
  Low risk: the MCP tool and REST endpoint should always return the same data; any
  divergence is a bug, not a feature.

## Migration Plan

Existing deployments require an `install.sh` re-run (`ghostship upgrade`) to
regenerate `initial-config.json` with the new Caddy paths. Until then, `/` and
`/api/crews` return 404 from the portal. No data migration required. No rollback
complexity — the transport routes are purely additive.
