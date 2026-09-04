# Changelog

## v0.3.0 (unreleased)

### TRN-103 — Portal is mandatory ⚠️ BREAKING

`ga-portal` (Caddy) is now a required architectural component and is always installed. The `GA_PORTAL_ENABLED` opt-in flag is removed.

- **BREAKING:** `GA_PORTAL_ENABLED` removed from config and code. There is no opt-out and no rollback to the pre-portal per-port uvicorn mode.
- **Migration:** any deployment that previously ran with `GA_PORTAL_ENABLED=false` must re-run `install.sh` to regenerate `compose.yml`; `ga-portal` is added to the stack and takes over ports 443/80 and the dashboard port range. No data migration.
- `install.sh` always generates the `ga-portal` service stanza, the Caddy `initial-config.json`, the `ga-portal-data` volume, and the portal health check.
- `transport/config.py`: `ga_portal_enabled` field and its `from_env()` binding removed.
- `transport/server.py`: `GA_PORTAL_ENABLED` module global and all its guards removed; the portal-enabled branch is now taken unconditionally in dashboard URL derivation, `launch(dashboard=True)`, the `POST /crews/{id}/dashboard` handler, and the startup Caddy re-registration loop.
- The other `GA_PORTAL_*` vars (`GA_PORTAL_TLS_MODE`, `GA_PORTAL_DOMAIN`, `GA_PORTAL_PORT`, `GA_PORTAL_HTTP_PORT`, `GA_PORTAL_ADMIN_URL`, `GA_PORTAL_SESSION_TTL_SECS`) are unchanged — they configure how the portal behaves, not whether it runs.
- Docs updated: `docs/caddy.md`, `docs/dashboard-proxy.md`, `docs/configuration.md`, `config/ghostship.conf.example`.

### TRN-101 — Portal-only dashboard proxy ⚠️ BREAKING

`launch(dashboard=True)` now requires `GA_PORTAL_ENABLED=true`. The transport's per-port uvicorn proxy threads are removed. Portal (`ga-portal`) is the sole dashboard proxy implementation.

- **BREAKING:** `launch(dashboard=True)` with `GA_PORTAL_ENABLED=false` returns an error: `"dashboard access requires GA_PORTAL_ENABLED=true; re-run install.sh and re-launch any existing dashboard crews — see docs/dashboard-proxy.md"`.
- **Removed:** `_start_dashboard_port_server`, `_stop_dashboard_port_server`, `_dashboard_app`, the per-port uvicorn daemon-thread pool, and their startup restore loop.
- **Removed:** `GA_DASHBOARD_PORT_ENABLED` config flag. Dashboard availability is now solely controlled by `GA_PORTAL_ENABLED`.
- `POST /crews/{id}/dashboard` returns 503 if `GA_PORTAL_ENABLED=false` (was: 503 if `GA_DASHBOARD_PORT_ENABLED=false`).
- Dashboard port range config (`GA_DASHBOARD_PORT_RANGE_START`, `GA_DASHBOARD_PORT_RANGE_SIZE`) retained — Portal still uses the transport's port pool.
- **Migration:** Set `GA_PORTAL_ENABLED=true`, re-run `install.sh`, nuke and re-launch any crews that had dashboards. See `docs/dashboard-proxy.md` for the full migration guide.

### TRN-92 — Caddy reverse proxy ⚠️ BREAKING (opt-in cutover)

`GA_PORTAL_ENABLED=true` is an opt-in, breaking cutover — no coexistence with the existing per-port mode. Re-run `install.sh` after enabling.

- `GA_PORTAL_ENABLED=true` adds a `ga-portal` container (vanilla `caddy:2` image) to the compose stack. It becomes the sole TLS terminator and auth gate for all ports.
- **Port ownership change:** Caddy binds the dashboard port range (default `64058–64107`) **and** ports 443/80. The transport no longer binds those ports. The transport's per-port uvicorn listener threads are not started.
- **Dashboard auth gating:** every dashboard port is now protected by a `forward_auth` → `gs_session` cookie gate. Unauthenticated requests redirect to `/login-ui`; `POST /dashboard-login` issues a session cookie when the operator's `GA_API_KEY` is correct.
- **MCP/file Bearer enforcement at the edge:** when `GA_API_KEY` is set, Caddy rejects bad or missing `Authorization: Bearer` on `/mcp*` and `/files/*` before requests reach the transport.
- **Four TLS modes:** `internal` (Caddy built-in CA, default), `tailscale` (browser-trusted `.ts.net` certs), `acme` (Let's Encrypt), `off` (plain HTTP). A one-time `caddy trust` step is required for `internal` mode; the cert path is printed by `install.sh` and surfaced by `ghostship status`.
- **New transport endpoints:** `GET /login-ui`, `POST /dashboard-login`, `GET /dashboard-auth`.
- **Dynamic Caddy server management:** `launch` registers a per-crew Caddy server via the admin API; `nuke` removes it. Transport startup re-registers servers from `crews.json` (idempotent). No Caddy restarts on crew changes.
- **Dashboard URLs become HTTPS:** `launch(dashboard=True)` returns `https://host:PORT/` when Caddy is enabled.
- **vm23 host Caddy retirement:** `ga-portal` replaces the host-level Caddy on vm23. Stop and disable the host Caddy before or alongside the `install.sh` cutover.
- New env vars: `GA_PORTAL_ENABLED`, `GA_PORTAL_ADMIN_URL`, `GA_PORTAL_TLS_MODE`, `GA_PORTAL_DOMAIN`, `GA_PORTAL_PORT`, `GA_PORTAL_HTTP_PORT`, `GA_PORTAL_SESSION_TTL_SECS`.
- Rate limiter extended with `dashboard_auth` endpoint (`GA_RATE_LIMIT_DASHBOARD_AUTH`, default 60 req/60 s).
- See [docs/caddy.md](docs/caddy.md) for setup, TLS modes, auth upgrade paths (`basicauth`, `caddy-security` SSO), and migration.

## v0.2.4 (2026-09-03)

### TRN-80 — Per-crew dashboard proxy
- `launch(dashboard=True)` allocates a dedicated port and returns a `dashboard_url` for the crew's browser UI (opt-in; `dashboard=False` by default)
- HTTP and WebSocket proxying to the KiroCrew SPA via per-port uvicorn daemon threads
- `POST/DELETE /crews/{id}/dashboard` REST API to attach or detach a dashboard port without nuke+relaunch
- Session cookie injection and CORS origin injection for browser authentication
- `GA_DASHBOARD_PORT_ENABLED`, `GA_DASHBOARD_PORT_RANGE_START`, `GA_DASHBOARD_PORT_RANGE_SIZE` environment variables
- Known limitation: dashboard ports are network-auth only (Tailscale/firewall); TRN-91/92 cover auth hardening

### TRN-89 — Timestamps on tool responses
- `dispatch` response includes `created_at`
- `pickup` (task-level) response includes `created_at`, `started_at`, `completed_at` (ISO 8601 UTC, `null` until reached)
- `captain status` response includes `last_checkin_at`
- Mail subjects (pickup, captain status) include `received_at` parsed from the message `Date` header

### TRN-90 — Bundle clone HEAD fix
- Fixed: `evac(bundle=True)` followed by `supply(bundle=True)` now correctly checks out the working tree when the bundle HEAD ref contains slashes (e.g. `release/0.2.4`)

### TRN-93 — Security hardening
- Admiral secret delivered via stdin instead of argv — no longer visible in `ps` or `/proc`
- `crews.json` stores an opaque sha256 identifier instead of the plaintext secret
- Container hardening: `no_new_privileges=True`, `cap_drop=[CAP_NET_RAW, CAP_SYS_ADMIN]`
- `KC_GATEWAY_TOKEN_TTL` validated on transport startup
- File-transfer audit logging

### TRN-94 — Broad mailbox skim
- `captain status` returns `agent_mail` covering all 8 mailboxes (ghost, spectre, banshee, wraith, reaper, raven, captain, admiral)
- Crew-level `pickup` (no `task_id`) returns `agent_subjects` covering all 8 mailboxes
- `pickup(agent="ghost", crew_id=...)` — new agent filter returns a single-inbox response with no task list
- `read_mail_subjects.py` updated to return `{subject, received_at}` dicts

### Fixes
- WebSocket pump: `asyncio.wait(FIRST_COMPLETED)` + cancel (replaces leaky `asyncio.gather`)
- httpx client pooling: one pooled `AsyncClient` per dashboard port (was re-created per request)
- DELETE dashboard atomicity: stop and release inside `_registry_lock`

---

## v0.2.3 and earlier

See git log for history prior to v0.2.4.
