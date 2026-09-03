# Design: TRN-92 — Caddy Reverse Proxy as Optional Transport Layer

## Context

See `proposal.md — Why` for motivation. Current state relevant to the design:

- The transport is a single Python/uvicorn process on port 64057. It runs as a container named `ga-transport` inside the `ga-net` Podman network.
- Dashboard UIs get per-port daemon-thread uvicorn servers (ports 64058–64107), each proxying to `gs-{id}:5476`. These spawn a new thread and asyncio event loop per crew.
- `BearerAuthMiddleware` enforces `GA_API_KEY` on every request. Dashboard ports are currently unauthenticated (TRN-91 gap).
- TLS is either absent (plain HTTP, the default) or via `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` on the transport itself (not widely used).
- The Caddy project already runs as a separate service on `vm23` (the academy host). That service is managed independently and listens on its own port — it does not share the `ga-net` Podman network with transport containers. The `ga-caddy` introduced here is a separate container joining `ga-net` only; the two cannot conflict.

## Goals / Non-Goals

**Goals:**
- One single exposed port for all external traffic (MCP, files, dashboard UIs, auth)
- TLS for all three target environments: local dev (internal CA), remote/ACME, Tailscale
- Cookie-gated dashboard login that browsers can use (no `Authorization` header required)
- Zero config changes for existing deployments (opt-in via `GA_CADDY_ENABLED=true`)
- Per-crew route registration/deregistration without Caddy restart

**Non-Goals:**
- OAuth/SSO integration (future work — the cookie-gate in this change is `GA_API_KEY`-backed, which is already what operators use today)
- Subdomain-per-crew (Option C from TRN-92 ticket) — requires wildcard DNS and complicates cert provisioning; path-prefix routing covers all current use cases
- Removing the per-port daemon-thread model — it stays as a fully functional fallback; no existing deployment is disrupted

## Decisions

### D1: Option B — Caddy as optional component, not always-on

**Chosen**: `GA_CADDY_ENABLED=false` (default). Operators opt in.

**Rationale**: The install base runs local, Tailscale-protected installs where TLS and browser auth are low-priority. Forcing Caddy on every install adds an image pull, a container, and a new dependency path for operators who just want MCP + headless crews. Optional solves the problems for operators who need it without regressing for those who don't.

**Alternatives considered**:
- *Always-on*: Simpler config, but breaks existing single-port installs and adds a mandatory external dependency.
- *Option A (status quo + TRN-91 bolt-on)*: Defers TLS entirely. Cookie auth bolted onto 50 separate per-port listeners is harder than doing it once in Caddy.
- *Option C (subdomain-per-crew)*: Cleaner origin isolation but requires wildcard DNS and complicates ACME provisioning. Not needed: SPAs work fine at a path prefix when their base URL is configured correctly, and the KiroCrew gateway already serves under a configurable root.

### D2: Route management via Caddy admin API, not static Caddyfile

**Chosen**: Transport calls `POST /config/apps/http/servers/ga/routes/.` to append a route, and `DELETE /config/id/crew-{id}` to remove it. Route objects carry `"@id": "crew-{id}"` for O(1) removal. No Caddy restarts.

**Rationale**: Caddy's admin API supports zero-downtime config mutation. Routes are appended to the live in-memory config; removal uses the `@id` shortcut path. This keeps the transport as the single source of truth for crew state (it already owns `crews.json`) — Caddy becomes a stateless routing plane driven by the transport.

**Alternative considered**: Regenerate a full Caddyfile and reload via `POST /load`. Works but is O(n) on every launch/nuke; requires the transport to maintain a full mental model of all routes and rebuild it on every operation. The append/delete API is cleaner.

**Concurrency note**: The Caddy admin API is ACID per-request but not transactionally isolated across concurrent appends. Concurrent `launch` calls could collide on the routes array. Mitigation: use `Etag`/`If-Match` optimistic locking (Caddy supports it — see [API docs](https://caddyserver.com/docs/api#concurrent-config-changes)) with a single retry on 412. Alternatively, serialize Caddy API calls with the existing `_registry_lock` — simpler, chosen as D2a.

**D2a (sub-decision)**: Serialize Caddy API calls inside `_registry_lock`. This is already held when the crew is written to `crews.json`, so extending it to cover the Caddy call makes the operation atomic with the registry write at no extra lock contention cost.

### D3: BearerAuthMiddleware retained for MCP, not replaced by Caddy

**Chosen**: Caddy forwards `Authorization: Bearer <key>` through to the transport unchanged. The transport's `BearerAuthMiddleware` continues to enforce it.

**Rationale**: Defence in depth. The transport should not become fully trusting of anything on `ga-net` — adding Caddy doesn't change the threat model for an operator who wants belt-and-suspenders auth. The transport can still be reached directly (e.g. from another container on `ga-net`) without Caddy in the path.

**Alternative**: Strip auth at Caddy and trust all `ga-net` traffic inside the transport. Cheaper but weakens the security boundary.

### D4: Cookie-gated login via transport endpoint + Caddy `forward_auth`

**Chosen**: Transport exposes `GET /dashboard-auth` (checked by Caddy as `forward_auth`) and `POST /dashboard-login` (accepts `ga_api_key`, issues `gs_session` cookie). Caddy's built-in `forward_auth` directive passes the `Cookie` header to `GET /dashboard-auth`; on 200 it proxies, on 401 it redirects to `/login-ui`.

**Rationale**: This is exactly what Caddy's `forward_auth` directive is designed for. No third-party plugin required — vanilla `caddy:2`. The transport already holds the API key and manages session cookies (it already does `mc_token_5476` for crew auth), so the pattern is consistent.

**Alternative considered**: `caddy-security` plugin (OAuth/OIDC). More powerful but adds a build dependency (Caddy's official Docker image doesn't include it; would need `xcaddy`), and the problem only requires `GA_API_KEY` parity for this release.

### D5: TLS mode via `GA_CADDY_TLS_MODE=internal|acme|off`

**Chosen**: Three modes baked into `initial-config.json` at install time:
- `internal`: `tls internal` — Caddy's built-in local CA. No DNS or external infra needed. Works for local and Tailscale installs.
- `acme`: ACME with `GA_CADDY_DOMAIN`. Works for public-IP remote installs. Port 80 must be reachable for HTTP-01 challenge.
- `off`: Caddy serves HTTP only. Useful when TLS is terminated upstream (e.g. a cloud load balancer in front of Caddy).

**Rationale**: Each environment has a clear TLS path. `internal` is the right default for the install base (local/Tailscale). `acme` is the answer for remote installs without forcing operators to manage certs manually. `off` exists for edge deployments.

### D6: `ga-caddy` data volume for cert persistence

**Chosen**: A named Podman volume `ga-caddy-data` is mounted at `/data` inside the `ga-caddy` container (standard Caddy data dir). This persists ACME certs and internal CA across container restarts.

**Rationale**: Without persistence, every restart triggers a new ACME challenge or regenerates the internal CA, breaking browser trust anchors.

### D7: Single `ga-caddy` port on `ga-net` for admin; no host binding for 2019

**Chosen**: Admin API port 2019 is only accessible on `ga-net` (transport → Caddy). It is not published to the host. The transport calls `http://ga-caddy:2019` over the internal network.

**Rationale**: Exposes the admin API only to the transport, which is the only caller. Prevents accidental exposure on the host.

## Architecture

```
                  ┌────────────────────────────────────────────────────────┐
  External        │  ga-caddy container (caddy:2 image, ga-net)            │
  traffic ──────▶ │  :443 (HTTPS)  :80 (HTTP/ACME)                        │
                  │                                                         │
                  │  Route table (managed via admin API):                  │
                  │  /mcp           ──────────────────▶ ga-transport:64057 │
                  │  /files/        ──────────────────▶ ga-transport:64057 │
                  │  /health        ──────────────────▶ ga-transport:64057 │
                  │  /dashboard-auth──────────────────▶ ga-transport:64057 │
                  │  /login-ui      ──────────────────▶ ga-transport:64057 │
                  │  /crews/alpha/ui/ (forward_auth ──▶ ga-transport:64057)│
                  │                   then proxy ─────▶ gs-alpha:5476      │
                  │  /crews/beta/ui/  (forward_auth ──▶ ga-transport:64057)│
                  │                   then proxy ─────▶ gs-beta:5476       │
                  │  ...                                                    │
                  └──────────────────────┬─────────────────────────────────┘
                                         │ admin API :2019 (ga-net only)
                  ┌──────────────────────▼─────────────────────────────────┐
                  │  ga-transport:64057 (Python/uvicorn, ga-net + 127.0.0.1)│
                  │  GA_API_KEY enforced by BearerAuthMiddleware            │
                  │  launch()  ──▶ POST /config/apps/http/servers/ga/routes │
                  │  nuke()    ──▶ DELETE /config/id/crew-{id}              │
                  │  /dashboard-auth  (forward_auth endpoint)               │
                  │  /login-ui        (login page)                          │
                  │  /dashboard-login (issues gs_session cookie)            │
                  │                                                         │
                  │  GA_DASHBOARD_PORT_ENABLED=false (default when Caddy on)│
                  │  (per-port uvicorn threads NOT started)                 │
                  └──────────────────────┬─────────────────────────────────┘
                                         │ http://gs-{id}:5476 (ga-net)
                  ┌──────────────────────▼─────────────────────────────────┐
                  │  gs-alpha:5476   gs-beta:5476   ...                    │
                  │  (crew containers, never exposed externally)           │
                  └────────────────────────────────────────────────────────┘
```

### Caddy initial config skeleton (JSON)

```json
{
  "admin": { "listen": "0.0.0.0:2019" },
  "apps": {
    "http": {
      "servers": {
        "ga": {
          "listen": [":443"],
          "routes": [
            {
              "@id": "ga-transport-mcp",
              "match": [{"path": ["/mcp*"]}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}]}]
            },
            {
              "@id": "ga-transport-files",
              "match": [{"path": ["/files/*"]}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}]}]
            },
            {
              "@id": "ga-transport-misc",
              "match": [{"path": ["/health", "/dashboard-auth", "/login-ui", "/dashboard-login"]}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}]}]
            }
          ]
        }
      }
    },
    "tls": {
      "automation": {
        "policies": [{"issuers": [{"module": "internal"}]}]
      }
    }
  }
}
```

Per-crew route appended at `launch`:

```json
{
  "@id": "crew-alpha",
  "match": [{"path": ["/crews/alpha/ui/*"]}],
  "handle": [
    {
      "handler": "subroute",
      "routes": [
        {
          "handle": [
            {
              "handler": "forward_auth",
              "uri": "http://ga-transport:64057/dashboard-auth",
              "copy_headers": ["Cookie"]
            }
          ]
        },
        {
          "handle": [
            {
              "handler": "reverse_proxy",
              "upstreams": [{"dial": "gs-alpha:5476"}],
              "headers": {
                "request": {
                  "set": {
                    "Cookie": ["mc_token_5476={cookie_value}"]
                  }
                }
              }
            }
          ]
        }
      ]
    }
  ]
}
```

**Note on crew session cookie injection**: The transport currently injects `mc_token_5476` in its Python proxy layer. In Caddy mode, this must shift: either the transport's `/dashboard-auth` endpoint returns the cookie value in a response header (e.g. `X-Crew-Cookie`) that Caddy then rewrites into the upstream request, or the per-crew route is constructed with the static cookie value baked in at registration time. The latter is simpler but requires re-registering the route if the cookie rotates. Recommended: transport's `/dashboard-auth` returns `X-Crew-Cookie: mc_token_5476=<value>` on 200; Caddy's `copy_headers` on `forward_auth` passes it to the proxy handler as a `Cookie` header. This mirrors the existing per-port Python logic.

### install.sh additions

- New env vars: `GA_CADDY_ENABLED` (default `false`), `GA_CADDY_TLS_MODE` (`internal`/`acme`/`off`), `GA_CADDY_DOMAIN`, `GA_CADDY_PORT` (default 443), `GA_CADDY_HTTP_PORT` (default 80).
- New section after the compose.yml generation block: write `initial-config.json` to `DATA_DIR/caddy/`.
- New `ga-caddy` service stanza in compose.yml (conditional on `GA_CADDY_ENABLED=true`):
  ```yaml
  ga-caddy:
    image: caddy:2
    container_name: ga-caddy
    restart: always
    ports:
      - "0.0.0.0:${GA_CADDY_HTTP_PORT:-80}:80"
      - "0.0.0.0:${GA_CADDY_PORT:-443}:443"
    networks:
      - ga-net
    volumes:
      - ${DATA_DIR}/caddy/initial-config.json:/config/initial-config.json:ro
      - ga-caddy-data:/data
    command: ["caddy", "run", "--config", "/config/initial-config.json", "--resume"]
  ```
- Remove `GA_DASHBOARD_PORT_RANGE_START–END` port bindings from `ga-transport` stanza when `GA_CADDY_ENABLED=true`.
- New `ga-caddy-data` named volume in compose.yml volumes section.

### transport/server.py additions

- `_caddy_admin_url()`: reads `GA_CADDY_ADMIN_URL` (default `http://ga-caddy:2019`).
- `_caddy_register_crew(crew_id, cookie_value)`: called inside `_registry_lock` at the end of `_finish_crew_setup`, after the cookie is minted. POSTs a route object to `/config/apps/http/servers/ga/routes/.`.
- `_caddy_deregister_crew(crew_id)`: called in `nuke` before registry removal. Calls `DELETE /config/id/crew-{crew_id}`. Logs a warning on failure, does not raise.
- `_handle_dashboard_auth(request)`: `GET /dashboard-auth` — reads `gs_session` cookie, checks in-memory token store, returns 200 or 401 + `X-Crew-Cookie` header on 200.
- `_handle_dashboard_login_post(request)`: `POST /dashboard-login` — validates `ga_api_key`, issues `gs_session` token.
- `_handle_login_ui(request)`: `GET /login-ui` — serves the minimal HTML login form.
- `_handle_dashboard_port_proxy` and `_start_dashboard_port_server` are conditionally suppressed when `GA_CADDY_ENABLED=True`.
- `dashboard_url` in `launch` and `crews` returns `https://<domain>/crews/{id}/ui/` when Caddy mode is active.

### transport/config.py additions

- `ga_caddy_enabled: bool = False`
- `ga_caddy_admin_url: str = "http://ga-caddy:2019"`
- `ga_caddy_tls_mode: str = "internal"` (`internal` | `acme` | `off`)
- `ga_caddy_domain: str = ""`
- `ga_caddy_port: int = 443`
- `ga_caddy_http_port: int = 80`

## Risks / Trade-offs

- **[Risk] `ga-caddy` startup race**: If the transport starts before `ga-caddy` is ready, route registration calls during `launch` will fail. → Mitigation: the transport retries Caddy admin API calls up to 3× with exponential backoff (total ~7s). Startup races are bounded.
- **[Risk] Cookie injection via `forward_auth` response headers requires Caddy 2.x feature verification**: The `copy_headers` field on `forward_auth` and header rewriting in the same route require care with Caddy 2's handler chain ordering. → Mitigation: prototype the route JSON against a running Caddy before committing to this exact structure. A simpler fallback: the transport's `/dashboard-auth` endpoint can return a redirect to a transport-owned cookie-injection page instead of using header rewriting.
- **[Risk] Existing `vm23/academy` Caddy conflict**: The existing Caddy on vm23 listens on whatever port it was configured for. The new `ga-caddy` container joins `ga-net` only and publishes to configurable ports (default 443/80). There is no conflict as long as both don't bind port 443 on the same host interface. → Mitigation: document that operators must either change `GA_CADDY_PORT` or use the existing vm23 Caddy as a pass-through for the transport (which is a valid and desirable topology — see Open Questions).
- **[Risk] `caddy --resume` loses routes after restart**: `caddy run --resume` reloads the last saved config from Caddy's data directory, which includes routes appended at runtime. If the data volume exists and the last saved state is good, routes survive restart. If the volume is recreated from scratch, routes are lost. → Mitigation: the transport's `_reconcile_registry` (called at startup) re-registers routes for all crews already in `crews.json`. The re-registration is idempotent (route `@id` already exists → Caddy returns 409 → transport handles gracefully).
- **[Trade-off] Path-prefix routing breaks SPAs that use `<base href="/">`**: If the KiroCrew dashboard SPA hard-codes `/` as its base, sub-routes under `/crews/{id}/ui/` will 404 on asset loads. → Mitigation: The SPA base URL must be configurable. This is a KiroCrew upstream concern. If `KIROCREW_BASE_URL=/crews/{id}/ui/` is injectable at crew-launch time, it resolves the issue. This should be confirmed before implementation begins (Open Question 2).

## Migration Plan

1. All existing deployments run unchanged — `GA_CADDY_ENABLED=false` is the default.
2. To opt in:
   - Set `GA_CADDY_ENABLED=true` in `ghostship.conf`.
   - Set `GA_CADDY_TLS_MODE=internal` (local/Tailscale) or `acme`+`GA_CADDY_DOMAIN` (remote).
   - Run `./install.sh --config ghostship.conf`.
   - For internal CA: run `caddy trust` (printed by install script) to add root CA to host/browser.
3. Existing crews survive — their routes are re-registered at transport startup via `_reconcile_registry`.
4. Rollback: set `GA_CADDY_ENABLED=false` and re-run `./install.sh`. Transport returns to direct + per-port mode.

## Open Questions

1. **vm23 topology**: Should `ga-caddy` be the TLS terminator, or should the existing vm23 Caddy proxy to `ga-transport:64057` with TLS handled at that outer layer? The latter avoids a second Caddy and is a valid deployment topology. If so, `GA_CADDY_ENABLED` may be unused on vm23 and the design serves only fresh remote installs. This doesn't change the design but affects the install documentation.

2. **KiroCrew SPA base URL**: Does `ghcr.io/kirodotdev/kirocrew:0.4.0` support a configurable base URL (e.g. `KIROCREW_BASE_URL=/crews/alpha/ui/`) so the dashboard SPA functions correctly under a path prefix in Caddy mode? Without this, path-prefix routing will break asset loads. If not supported, the subdomain-per-crew approach (Option C) becomes more attractive. This must be confirmed before implementation tasks are checked off.

3. **Per-port + Caddy coexistence**: Can a single crew have both a per-port listener (`dashboard_url = http://host:PORT/`) and a Caddy path route (`https://host/crews/{id}/ui/`) simultaneously? Current design says no (per-port suppressed when Caddy enabled), but there may be a use case for offering both during a migration window.
