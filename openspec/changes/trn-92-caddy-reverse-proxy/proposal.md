## Why

The current transport serves plain HTTP, has no TLS path, and relies on network-layer isolation alone to protect crew dashboard UIs — the per-crew dashboard ports (64058–64107) are completely unauthenticated (TRN-91). Three problems — no browser-friendly dashboard auth, no TLS, and no programmable edge — converge on the same structural gap: there is no reverse-proxy layer between the public network and the transport's routing. Bundling Caddy as an optional, auto-configured transport layer makes Caddy the TLS terminator **and the first auth gate** for all traffic, without requiring an external deployment dependency and without disturbing the per-port dashboard model the KiroCrew SPA requires.

## What Changes

- **New `ga-caddy` container** added to the compose stack (opt-in via `GA_CADDY_ENABLED=true`). When enabled, `ga-caddy` binds all public ports — 443/80 **and the dashboard port range 64058–64107** — and is the sole TLS terminator.
- **Dashboard routing stays port-based.** The KiroCrew SPA requires a root origin (path-prefix `/crews/{id}/ui/` was tried and confirmed broken; subdomain routing does not work on localhost). Each crew UI keeps its dedicated port. When Caddy is enabled, **Caddy binds those ports** (instead of the transport's per-port uvicorn listeners), adds TLS + cookie-gated auth on each, and proxies to `http://gs-{id}:5476/`. There is exactly one dashboard routing mode.
- **The transport's per-port uvicorn listener threads are removed when Caddy is enabled.** Caddy owns the port bindings; the transport only maintains the port↔crew mapping and pushes it to Caddy via the admin API at `launch`/`nuke`.
- **Caddy admin API integration** in `transport/server.py`: `launch` registers a per-crew Caddy server (`PUT /id/crew-{id}`) bound to the allocated port; `nuke` removes it (`DELETE /id/crew-{id}`). Zero-downtime, no Caddy restart.
- **MCP and file-transfer routes** (`/mcp`, `/files/*`) are proxied through Caddy. When `GA_API_KEY` is set, **Caddy enforces the Bearer token at the edge** and rejects bad requests with 401 before they reach the Python process. `BearerAuthMiddleware` is retained for defence in depth.
- **Dashboard auth via Caddy `forward_auth`** (default): Caddy calls `GET /dashboard-auth` on the transport before proxying each dashboard request; the transport validates a `gs_session` cookie and returns 200/401. A login page at `/login-ui` posts `ga_api_key` to `POST /dashboard-login`. No Caddy plugin required. `basicauth` and the `caddy-security` OIDC/OAuth2 plugin are documented as supported upgrade paths (a Caddy-config change, not a transport rewrite).
- **TLS**: `GA_CADDY_TLS_MODE=internal|tailscale|acme|off`. `internal` (default) — Caddy built-in CA, works anywhere, one-time `caddy trust`; `tailscale` — real trusted `.ts.net` certs via Tailscale ACME (vm23/academy); `acme` — public Let's Encrypt with `GA_CADDY_DOMAIN`; `off` — plain HTTP. In `internal` mode the root CA cert path is surfaced by install output and `ghostship status`.
- **`install.sh` updated** to write a Caddy `initial-config.json`, add the `ga-caddy` service (binding public + dashboard ports) to the generated `compose.yml`, and move the dashboard port-range binding off `ga-transport` — all conditional on `GA_CADDY_ENABLED=true`.
- **BREAKING**: `GA_CADDY_ENABLED=true` is a clean cutover — no coexistence with the transport's per-port listeners, no migration window. On vm23 the pre-existing host-level Caddy is retired; `ga-caddy` takes over inbound traffic.
- **Docs**: new `docs/caddy.md`, updates to `docs/dashboard-proxy.md` (breaking-change note), `docs/auth.md`, `docs/configuration.md`, and release notes.

## Capabilities

### New Capabilities

- `transport/caddy-proxy`: Caddy container lifecycle, initial JSON config generation, per-crew dashboard-server registration/deregistration via the Caddy admin API (`PUT`/`DELETE /id/crew-{id}`), and edge Bearer enforcement for MCP/file routes.
- `transport/dashboard-auth`: `forward_auth` flow — the transport's `/dashboard-auth` validation endpoint, `/login-ui` login page, and `/dashboard-login` cookie-issuing endpoint; the `gs_session` cookie lifecycle. Closes TRN-91.
- `transport/tls`: Auto-provisioned TLS via Caddy in four modes (`internal`/`tailscale`/`acme`/`off`), with internal-CA root-cert path surfacing.

### Modified Capabilities

- `transport/dashboard-proxy`: When Caddy is enabled, Caddy binds the per-crew dashboard ports and the transport's per-port uvicorn listeners are not started. Single mode (port-based). The per-port uvicorn model is used only when Caddy is disabled.

## Impact

- `install.sh`: adds `GA_CADDY_ENABLED`, `GA_CADDY_TLS_MODE`, `GA_CADDY_DOMAIN`, `GA_CADDY_PORT`, `GA_CADDY_HTTP_PORT`; writes `initial-config.json`; adds `ga-caddy` service (binds 443/80 + dashboard range, injects `GA_API_KEY` env); moves the dashboard range binding off `ga-transport`; prints the internal-CA root path.
- `transport/server.py`: `_caddy_register_crew`/`_caddy_deregister_crew` in `launch`/`nuke`; `_handle_dashboard_auth`/`_handle_dashboard_login_post`/`_handle_login_ui`; suppress per-port uvicorn threads when Caddy enabled; `_reconcile_registry` re-registers Caddy servers on startup.
- `transport/config.py`: new fields `ga_caddy_enabled`, `ga_caddy_admin_url`, `ga_caddy_tls_mode`, `ga_caddy_domain`, `ga_caddy_port`, `ga_caddy_http_port`.
- `transport/Containerfile`: no change (Caddy runs as a separate `caddy:2` container; the `caddy-security` SSO path is a separate `xcaddy` build, documented not built).
- `ghostship` CLI: `ghostship status` surfaces the internal-CA root cert path.
- Compose template: new `ga-caddy` service + `ga-caddy-data` volume; Caddy admin port (2019) internal-only.
- Docs: `docs/caddy.md` (new), `docs/dashboard-proxy.md`, `docs/auth.md`, `docs/configuration.md`, release notes (breaking change).
- Existing deployments unaffected: `GA_CADDY_ENABLED` defaults to `false`.
