# Design: TRN-92 — Caddy Reverse Proxy as Optional Transport Layer

## Context

See `proposal.md — Why` for motivation. Current state relevant to the design:

- The transport is a single Python/uvicorn process on port 64057. It runs as a container named `ga-transport` inside the `ga-net` Podman network.
- Dashboard UIs get per-port daemon-thread uvicorn servers (ports 64058–64107), each proxying to `gs-{id}:5476`. These spawn a new thread and asyncio event loop per crew. The per-port model exists **because the KiroCrew dashboard SPA requires a root origin** — it does not work under a path prefix (`/crews/{id}/ui/`), which was tried and confirmed broken. Each crew UI therefore owns a full origin (`host:PORT/`).
- `BearerAuthMiddleware` enforces `GA_API_KEY` on every request to the main transport port (64057). Dashboard ports are currently unauthenticated (TRN-91 gap).
- TLS is either absent (plain HTTP, the default) or via `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` on the transport itself (not widely used).
- The Caddy project already runs as a separate host-level service on `vm23` (the academy host), managed independently. This design's `ga-caddy` container **replaces** that host Caddy on vm23 (see D8).

## Goals / Non-Goals

**Goals:**
- TLS for all target environments: local dev (internal CA), remote/ACME, Tailscale
- Cookie-gated dashboard login that browsers can use (no `Authorization` header required), applied per crew UI port
- Preserve the per-port dashboard model (a root origin per crew), which the SPA requires
- Zero config changes for existing deployments (opt-in via `GA_CADDY_ENABLED=true`)
- Per-crew port↔crew mapping registered/deregistered in Caddy without a Caddy restart

**Non-Goals:**
- Subdomain-per-crew routing — dropped: subdomains don't work on localhost, and the port-per-crew model already gives each SPA a root origin. There is exactly one dashboard routing mode (port).
- Path-prefix dashboard routing (`/crews/{id}/ui/`) — confirmed broken by the SPA's root-origin requirement.
- OAuth/SSO integration (future work — the cookie-gate in this change is `GA_API_KEY`-backed, which is already what operators use today)
- Coexistence of Caddy mode and the transport's per-port uvicorn listeners — `GA_CADDY_ENABLED=true` is a clean cutover (see D9).

## Decisions

### D1: Option B — Caddy as optional component, not always-on

**Chosen**: `GA_CADDY_ENABLED=false` (default). Operators opt in.

**Rationale**: The install base runs local, Tailscale-protected installs where TLS and browser auth are low-priority. Forcing Caddy on every install adds an image pull, a container, and a new dependency path for operators who just want MCP + headless crews. Optional solves the problems for operators who need it without regressing for those who don't.

**Alternatives considered**:
- *Always-on*: Simpler config, but breaks existing installs and adds a mandatory external dependency.
- *Option A (status quo + TRN-91 bolt-on)*: Defers TLS entirely. Cookie auth bolted onto the transport's own per-port listeners is workable, but Caddy binding the ports directly gives TLS + auth in one component.
- *Option C (subdomain-per-crew)*: Dropped — see Non-Goals.

### D2: MCP/file route management via Caddy admin API, not static Caddyfile

**Chosen**: The MCP, file, and health/auth routes live on Caddy's main port (443). Per-crew **dashboard ports** are managed via the Caddy admin API: `launch` calls `POST /config/apps/http/servers/.../` (or `PUT /id/...`) to add a new server listening on the crew's allocated port and proxying to `gs-{id}:5476`; `nuke` calls `DELETE /config/id/crew-{id}` to remove it. Server objects carry `"@id": "crew-{id}"` for O(1) removal. No Caddy restarts.

**Rationale**: Caddy's admin API supports zero-downtime config mutation. The transport remains the single source of truth for crew state (it already owns `crews.json` and the port pool) — Caddy becomes a stateless port-binding + TLS + auth plane driven by the transport.

**Alternative considered**: Regenerate a full Caddyfile and reload via `POST /load`. Works but is O(n) on every launch/nuke and requires the transport to rebuild the full config each time. The add/delete-by-`@id` API is cleaner.

**Concurrency note**: The Caddy admin API is ACID per-request but not transactionally isolated across concurrent changes. Mitigation: serialize Caddy API calls inside the existing `_registry_lock` (D2a) — the lock is already held during port allocation and the `crews.json` write, so the Caddy call is atomic with those at no extra contention cost. `Etag`/`If-Match` optimistic locking is available as a fallback if lock contention becomes an issue.

**D2a (sub-decision)**: Serialize Caddy admin API calls inside `_registry_lock`.

### D3: BearerAuthMiddleware retained for MCP, not replaced by Caddy

**Chosen**: Caddy forwards `Authorization: Bearer <key>` through to the transport unchanged on the MCP/file routes. The transport's `BearerAuthMiddleware` continues to enforce it.

**Rationale**: Defence in depth. The transport should not become fully trusting of anything on `ga-net`. The transport can still be reached directly (e.g. from another container on `ga-net`) without Caddy in the path.

**Alternative**: Strip auth at Caddy and trust all `ga-net` traffic inside the transport. Cheaper but weakens the security boundary.

### D4: Dashboard auth — `forward_auth` default, `basicauth` and `caddy-security` alternatives

**Chosen (default): `forward_auth`.** Each per-crew dashboard server in Caddy runs a `forward_auth` check to `GET /dashboard-auth` on the transport before proxying to the crew gateway. The transport validates a `gs_session` cookie and returns 200 (allow) or 401 (deny). On 401, Caddy redirects the browser to `/login-ui`, which posts `ga_api_key` to `POST /dashboard-login`; the transport issues the `gs_session` cookie. All auth logic stays in the transport — **no Caddy plugin required**, vanilla `caddy:2`. This closes the TRN-91 gap: every dashboard port becomes auth-gated, consistent with `GA_API_KEY`.

**Alternatives documented as supported upgrade paths (not defaults):**
- **Caddy `basicauth`** — Caddy handles HTTP Basic Auth natively against a hashed password. No transport changes, no session (credentials on every request). Acceptable for ops tooling; simpler but less friendly for a browser SPA. An operator can swap the per-crew server's `forward_auth` handler for a `basicauth` handler in the Caddyfile/JSON without touching transport code.
- **`caddy-security` plugin (OIDC/OAuth2)** — full SSO via Google, GitHub, Tailscale identity, Authentik, etc. Requires building the Caddy image with the `caddy-security` plugin (via `xcaddy`). Most powerful, adds a plugin + config dependency. **Documented as a first-class upgrade path**, not an afterthought: the `docs/caddy.md` "SSO" section describes the `xcaddy` build and the config swap, so an operator who wants SSO knows exactly what changes (Caddy config only — see D10 posture).

**Rationale**: `forward_auth` is exactly what Caddy's directive is designed for, keeps the session logic where the API key already lives, and needs no plugin. Offering `basicauth` and `caddy-security` as explicit, documented swaps means the auth strength is a Caddy-config decision, not a transport rewrite — the architectural win the Admiral wants.

### D5: TLS mode via `GA_CADDY_TLS_MODE=internal|tailscale|acme|off`

**Chosen**: Four modes baked into `initial-config.json` at install time:
- `internal` (default): Caddy's built-in CA issues self-signed certs. Works on localhost, private IPs, Tailscale addresses, and any hostname — no DNS or external infra needed. The operator trusts Caddy's root CA once (`caddy trust`), after which every crew cert is trusted automatically. Best default for homelab/private-network deployments.
- `tailscale`: Caddy provisions real browser-trusted certs for `.ts.net` hostnames via Tailscale's ACME endpoint. Requires the Tailscale daemon present on the host. Ideal for vm23/academy deployments — no cert-trust step needed.
- `acme`: Standard Let's Encrypt / public ACME. For internet-facing deployments with real DNS. Requires `GA_CADDY_DOMAIN` set and ports 80/443 reachable for the ACME challenge.
- `off`: Plain HTTP, no TLS. For local dev, or when an upstream terminator already handles TLS.

TLS applies to every listener Caddy owns — the main port and every per-crew dashboard port.

**CA path surfacing (internal mode)**: When `GA_CADDY_TLS_MODE=internal`, operators need the Caddy root CA cert to complete the one-time trust step. The install script prints its path, and `ghostship status` surfaces it. The cert lives in the `ga-caddy-data` volume at the standard Caddy path `/data/caddy/pki/authorities/local/root.crt`; the install output and `ghostship status` translate that to the host-visible location (the `ga-caddy-data` volume mountpoint) so operators know exactly where to point `caddy trust` or their OS/browser trust store.

**Rationale**: Each environment has a clear TLS path. `internal` is the right default for the private-network install base. `tailscale` gives vm23/academy real trusted certs with zero trust-step friction. `acme` is the answer for public internet-facing installs. `off` exists for edge/dev deployments.

### D6: `ga-caddy` data volume for cert persistence

**Chosen**: A named Podman volume `ga-caddy-data` is mounted at `/data` inside the `ga-caddy` container (standard Caddy data dir). This persists ACME certs, the internal CA, and the resumed runtime config across container restarts.

**Rationale**: Without persistence, every restart triggers a new ACME challenge or regenerates the internal CA, breaking browser trust anchors.

### D7: Caddy admin API bound to `ga-net` only; no host binding for 2019

**Chosen**: Admin API port 2019 is only accessible on `ga-net` (transport → Caddy). It is not published to the host. The transport calls `http://ga-caddy:2019` over the internal network.

**Rationale**: Exposes the admin API only to the transport, which is the only caller. Prevents accidental exposure on the host.

### D8: `ga-caddy` is the sole TLS terminator; vm23 host Caddy is retired

**Chosen**: When `GA_CADDY_ENABLED=true`, `ga-caddy` takes over all inbound traffic (443/80 and the dashboard port range). The pre-existing host-level Caddy on vm23 is no longer needed and should be retired once `ga-caddy` is active.

**Rationale** (Admiral decision, Q1): One TLS terminator, not two. Running both is redundant and risks port conflicts. `ga-caddy` publishes the public ports directly; the vm23 operator stops/removes the host Caddy as part of the cutover.

### D9: Clean cutover — no per-port + Caddy coexistence

**Chosen**: When `GA_CADDY_ENABLED=true`, the transport's per-port uvicorn listener threads are **not started**; Caddy owns every dashboard port binding. There is no mode where both run simultaneously. Flipping the flag and re-running `install.sh` is the cutover.

**Rationale** (Admiral decision, Q3): A migration window with both proxies live on the same ports is impossible (port conflict) and unnecessary. The flag is a clean switch. This is a **breaking change** — documented as such.

### D10: MCP/file auth enforced at Caddy + general auth posture

**Chosen**: When `GA_CADDY_ENABLED=true` and `GA_API_KEY` is set, Caddy enforces the Bearer token on the `/mcp*` and `/files/*` routes **before** the request reaches the transport. A request without the correct `Authorization: Bearer <GA_API_KEY>` is rejected at Caddy with 401 and never touches the Python process. The transport keeps `BearerAuthMiddleware` for defence in depth (D3) — it still runs, so a direct `ga-net` call to the transport is still checked.

**Caddy enforcement mechanism**: a matcher on the main-server MCP/file routes that requires the `Authorization` header to equal `Bearer {env.GA_API_KEY}` (Caddy reads `GA_API_KEY` from its own environment, injected via the compose stanza). Requests that don't match are handled by a `static_response` returning 401 with `WWW-Authenticate: Bearer`. (A `basicauth` block with the API key as the password is an equivalent alternative for tooling that can't send a Bearer header.)

**General auth posture** (documented in `design.md` and `docs/auth.md`):

| | `GA_CADDY_ENABLED=false` (today) | `GA_CADDY_ENABLED=true` |
|---|---|---|
| MCP / files | `BearerAuthMiddleware` when `GA_API_KEY` set | Caddy rejects bad Bearer at the edge; transport `BearerAuthMiddleware` is defence-in-depth |
| Dashboard ports | **unauthenticated** (TRN-91 gap) | Caddy `forward_auth` → `gs_session` cookie gate on every port |
| TLS | none, or direct `GA_TLS_*` | Caddy-terminated on all ports (D5) |
| Upgrade to SSO | requires transport code | **Caddy-config change only** (swap `forward_auth`→`caddy-security`) — the architectural win |

**Rationale** (Admiral direction): Caddy becomes the first auth gate for all traffic, shrinking the unauthenticated attack surface reaching the Python process to zero on the public path. Because auth strength lives in Caddy config, moving from API-key → Basic → full SSO is a config edit, not a transport rewrite.

## Architecture

Two layers of Caddy routing:
1. **Main port (443/80)** — a fixed server for MCP, files, health, and the auth/login endpoints. Static, written at install time.
2. **Per-crew dashboard ports (64058–64107)** — one Caddy server per allocated port, added/removed dynamically via the admin API as crews launch/nuke. Each has TLS + `forward_auth` + reverse_proxy to `gs-{id}:5476`. This preserves the root-origin-per-crew model the SPA requires.

```
                  ┌────────────────────────────────────────────────────────┐
  External        │  ga-caddy container (caddy:2 image, ga-net)            │
  traffic ──────▶ │                                                         │
                  │  MAIN SERVER  :443 (HTTPS)  :80 (HTTP/ACME)            │
                  │    /mcp*          ────────────────▶ ga-transport:64057 │
                  │    /files/*       ────────────────▶ ga-transport:64057 │
                  │    /health        ────────────────▶ ga-transport:64057 │
                  │    /dashboard-auth────────────────▶ ga-transport:64057 │
                  │    /login-ui      ────────────────▶ ga-transport:64057 │
                  │    /dashboard-login───────────────▶ ga-transport:64057 │
                  │                                                         │
                  │  PER-CREW DASHBOARD SERVERS (dynamic, one per port):   │
                  │    :64058 (TLS)  forward_auth ──▶ ga-transport:64057   │
                  │                  then proxy   ──▶ gs-alpha:5476        │
                  │    :64059 (TLS)  forward_auth ──▶ ga-transport:64057   │
                  │                  then proxy   ──▶ gs-beta:5476         │
                  │    ...                                                  │
                  └──────────────────────┬─────────────────────────────────┘
                                         │ admin API :2019 (ga-net only)
                                         │ launch → PUT /id/crew-{id} (add server on its port)
                                         │ nuke   → DELETE /id/crew-{id}
                  ┌──────────────────────▼─────────────────────────────────┐
                  │  ga-transport:64057 (Python/uvicorn, ga-net + 127.0.0.1)│
                  │  GA_API_KEY enforced by BearerAuthMiddleware            │
                  │  owns the port pool + crews.json                        │
                  │  launch()  ──▶ allocate port, PUT Caddy server @id      │
                  │  nuke()    ──▶ DELETE Caddy server @id, release port    │
                  │  /dashboard-auth  (forward_auth endpoint)               │
                  │  /login-ui        (login page)                          │
                  │  /dashboard-login (issues gs_session cookie)            │
                  │                                                         │
                  │  Per-port uvicorn listener threads NOT started          │
                  │  (Caddy owns the port bindings when GA_CADDY_ENABLED)   │
                  └──────────────────────┬─────────────────────────────────┘
                                         │ http://gs-{id}:5476 (ga-net)
                  ┌──────────────────────▼─────────────────────────────────┐
                  │  gs-alpha:5476   gs-beta:5476   ...                    │
                  │  (crew containers, never exposed externally)           │
                  └────────────────────────────────────────────────────────┘
```

### Caddy initial config skeleton (JSON) — main server

```json
{
  "admin": { "listen": "0.0.0.0:2019" },
  "apps": {
    "http": {
      "servers": {
        "ga-main": {
          "listen": [":443"],
          "routes": [
            {
              "@id": "ga-transport-mcp",
              "match": [{"path": ["/mcp*"], "header": {"Authorization": ["Bearer {env.GA_API_KEY}"]}}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}]}]
            },
            {
              "@id": "ga-transport-files",
              "match": [{"path": ["/files/*"], "header": {"Authorization": ["Bearer {env.GA_API_KEY}"]}}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}]}]
            },
            {
              "@id": "ga-mcp-files-reject",
              "match": [{"path": ["/mcp*", "/files/*"]}],
              "handle": [{"handler": "static_response", "status_code": 401, "headers": {"Www-Authenticate": ["Bearer"]}, "body": "Unauthorized"}]
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

### Per-crew dashboard server added at `launch` (via `PUT /config/apps/http/servers/crew-{id}` or `PUT /id/...`)

A whole HTTP server bound to the crew's allocated port, carrying `"@id": "crew-{id}"`:

```json
{
  "@id": "crew-alpha",
  "listen": [":64058"],
  "routes": [
    {
      "handle": [
        {
          "handler": "subroute",
          "routes": [
            {
              "handle": [
                {
                  "handler": "forward_auth",
                  "uri": "http://ga-transport:64057/dashboard-auth",
                  "copy_headers": ["X-Crew-Cookie"]
                }
              ]
            },
            {
              "handle": [
                {
                  "handler": "reverse_proxy",
                  "upstreams": [{"dial": "gs-alpha:5476"}]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

**Crew session cookie injection**: The transport currently injects `mc_token_5476` in its Python per-port proxy layer. In Caddy mode this shifts to the `forward_auth` response: the transport's `/dashboard-auth` endpoint returns `X-Crew-Cookie: mc_token_5476=<value>` on a 200, and Caddy's `copy_headers` carries it into the upstream request to the crew gateway. The crew the request belongs to is identified by the incoming port (Caddy passes it, or `/dashboard-auth` maps the port→crew from the registry). This mirrors the existing per-port Python logic exactly, just relocated into Caddy's handler chain.

### install.sh additions

- New env vars: `GA_CADDY_ENABLED` (default `false`), `GA_CADDY_TLS_MODE` (`internal`/`acme`/`off`), `GA_CADDY_DOMAIN`, `GA_CADDY_PORT` (default 443), `GA_CADDY_HTTP_PORT` (default 80).
- New section after the compose.yml generation block: write `initial-config.json` (main server only) to `DATA_DIR/caddy/`.
- New `ga-caddy` service stanza in compose.yml (conditional on `GA_CADDY_ENABLED=true`). It binds 443/80 **and the dashboard port range** (since Caddy, not the transport, now owns those ports):
  ```yaml
  ga-caddy:
    image: caddy:2
    container_name: ga-caddy
    restart: always
    ports:
      - "0.0.0.0:${GA_CADDY_HTTP_PORT:-80}:80"
      - "0.0.0.0:${GA_CADDY_PORT:-443}:443"
      - "${GA_DASHBOARD_PORT_RANGE_START:-64058}-${_DASHBOARD_PORT_END}:${GA_DASHBOARD_PORT_RANGE_START:-64058}-${_DASHBOARD_PORT_END}"
    networks:
      - ga-net
    environment:
      GA_API_KEY: "${GA_API_KEY:-}"
    volumes:
      - ${DATA_DIR}/caddy/initial-config.json:/config/initial-config.json:ro
      - ga-caddy-data:/data
    command: ["caddy", "run", "--config", "/config/initial-config.json", "--resume"]
  ```
- **Remove** the dashboard port range binding from the `ga-transport` stanza when `GA_CADDY_ENABLED=true` — Caddy owns those ports now, and both binding them is a conflict.
- New `ga-caddy-data` named volume in compose.yml volumes section.

### transport/server.py changes

- `_caddy_admin_url()`: reads `cfg.ga_caddy_admin_url` (default `http://ga-caddy:2019`).
- `_caddy_register_crew(crew_id, port)`: called inside `_registry_lock` at the end of `launch` after the port is allocated. `PUT`s a whole server object bound to `port` with `@id: crew-{id}` to the Caddy admin API. Retries 3× with backoff; logs warning on failure.
- `_caddy_deregister_crew(crew_id)`: called in `nuke` before registry removal. `DELETE /config/id/crew-{crew_id}`. Handles 404 gracefully; logs warning, does not raise.
- `_handle_dashboard_auth(request)`: `GET /dashboard-auth` — reads `gs_session` cookie, checks the in-memory token store, returns 200 + `X-Crew-Cookie` (the crew's `mc_token_5476`) on success or 401 on failure. Determines the crew from the incoming dashboard port.
- `_handle_dashboard_login_post(request)`: `POST /dashboard-login` — validates `ga_api_key`, issues a `gs_session` token cookie.
- `_handle_login_ui(request)`: `GET /login-ui` — serves the minimal HTML login form.
- **`_start_dashboard_port_server` / `_handle_dashboard_port_proxy` / the per-port uvicorn threads are NOT started when `cfg.ga_caddy_enabled=True`.** Caddy owns the port bindings; the transport only maintains the port↔crew mapping and pushes it to Caddy.
- `dashboard_url` in `launch` and `crews` returns `https://<host>:<port>/` (the same per-port URL shape as today, but HTTPS via Caddy) when Caddy mode is active.

### transport/config.py additions

- `ga_caddy_enabled: bool = False`
- `ga_caddy_admin_url: str = "http://ga-caddy:2019"`
- `ga_caddy_tls_mode: str = "internal"` (`internal` | `tailscale` | `acme` | `off`)
- `ga_caddy_domain: str = ""`
- `ga_caddy_port: int = 443`
- `ga_caddy_http_port: int = 80`

## Risks / Trade-offs

- **[Risk] `ga-caddy` startup race**: If the transport starts before `ga-caddy` is ready, per-crew server registration during `launch` fails. → Mitigation: retry Caddy admin API calls up to 3× with exponential backoff (~7s total). Startup races are bounded.
- **[Risk] `forward_auth` cookie-injection chain ordering in Caddy 2.x**: `copy_headers` on `forward_auth` plus the downstream reverse_proxy must be verified against a running Caddy. → Mitigation: prototype the server JSON against a live Caddy before committing. Fallback: `/dashboard-auth` redirects to a transport-owned cookie-set page rather than header rewriting.
- **[Risk] `caddy --resume` loses dynamically-added servers after a volume wipe**: Runtime-added per-crew servers are persisted to Caddy's data dir and restored by `--resume`. If `ga-caddy-data` is recreated from scratch, they are lost. → Mitigation: the transport's `_reconcile_registry` (startup) re-registers a Caddy server for every crew in `crews.json` that has an allocated dashboard port. Re-registration is idempotent (409 on existing `@id` handled gracefully).
- **[Breaking change] Port ownership moves from transport to Caddy**: When `GA_CADDY_ENABLED=true`, the transport no longer binds 64058–64107; Caddy does. Enabling the flag on a running install requires a reinstall (`install.sh` regenerates compose.yml so only Caddy binds the range). → Mitigation: documented as a breaking change in release notes and `docs/dashboard-proxy.md`. Clean cutover, no coexistence (D9).

## Migration Plan

1. All existing deployments run unchanged — `GA_CADDY_ENABLED=false` is the default.
2. To opt in (**breaking cutover**):
   - Set `GA_CADDY_ENABLED=true` in `ghostship.conf`.
   - Set `GA_CADDY_TLS_MODE=internal` (local/Tailscale) or `acme`+`GA_CADDY_DOMAIN` (remote).
   - On vm23: stop/remove the pre-existing host-level Caddy (D8) — `ga-caddy` takes over inbound traffic.
   - Run `./install.sh --config ghostship.conf`. The regenerated compose.yml binds the dashboard port range to `ga-caddy`, not `ga-transport`.
   - For internal CA: run `caddy trust` (printed by install script) to add the root CA to host/browser.
3. Existing crews survive — their Caddy dashboard servers are re-registered at transport startup via `_reconcile_registry`.
4. Rollback: set `GA_CADDY_ENABLED=false` and re-run `./install.sh`. Transport returns to direct + per-port uvicorn mode and re-binds the range itself.

## Open Questions

All prior open questions are resolved (Admiral decisions):
- **Q1 (vm23 topology)** → D8: `ga-caddy` is the sole TLS terminator; the host Caddy on vm23 is retired.
- **Q2 (SPA base URL / path-prefix)** → confirmed broken. Dashboard routing stays port-based (root origin per crew); path-prefix and subdomain approaches are both dropped.
- **Q3 (coexistence)** → D9: clean cutover, no migration window. Documented as a breaking change.
