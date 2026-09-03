## 1. Config and Environment

- [x] 1.1 Add new fields to `transport/config.py`: `ga_caddy_enabled`, `ga_caddy_admin_url`, `ga_caddy_tls_mode` (`internal`/`tailscale`/`acme`/`off`, default `internal`), `ga_caddy_domain`, `ga_caddy_port`, `ga_caddy_http_port`; add `from_env()` reads with documented defaults; validate `ga_caddy_tls_mode` against the four allowed values (warn + fall back to `internal` on an unknown value).
- [x] 1.2 Add `GA_CADDY_*` variable documentation to `config/ghostship.conf.example` with comments matching the existing style (all four TLS modes described).
- [x] 1.3 Add `GA_CADDY_*` variable documentation to `docs/configuration.md`, including the internal-CA root-cert trust step and the four TLS modes.

## 2. Caddy Admin API — MCP/File Edge Auth

- [x] 2.1 Implement `_caddy_admin_url()` helper reading `cfg.ga_caddy_admin_url` (default `http://ga-caddy:2019`).
- [x] 2.2 Generate the main-server `/mcp*` and `/files/*` routes with a Bearer matcher (`Authorization: Bearer {env.GA_API_KEY}`) plus a catch-all 401 `static_response` route, in the `initial-config.json` writer (task 5.3). Verify a bad/missing token is rejected at Caddy.
- [x] 2.3 Ensure the `ga-caddy` compose stanza injects `GA_API_KEY` into Caddy's environment so `{env.GA_API_KEY}` resolves.

## 3. Caddy Admin API — Per-Crew Dashboard Servers

- [x] 3.1 Implement `_caddy_register_crew(crew_id, port)`: builds a Caddy HTTP-server JSON object (`@id: crew-{crew_id}`, `listen: [":{port}"]`, `forward_auth` sub-handler to `/dashboard-auth` with `copy_headers: ["X-Crew-Cookie"]`, then `reverse_proxy` to `gs-{crew_id}:5476`), `PUT`s it to the Caddy admin API, retries 3× with backoff, logs a warning on failure (does not raise).
- [x] 3.2 Implement `_caddy_deregister_crew(crew_id)`: `DELETE /config/id/crew-{crew_id}`, handles 404 gracefully, logs a warning on other failures.
- [x] 3.3 Call `_caddy_register_crew` inside `_registry_lock` in `launch` after the dashboard port is allocated, when `cfg.ga_caddy_enabled` and `dashboard=True`.
- [x] 3.4 Call `_caddy_deregister_crew` in `nuke` (before registry removal / port release) when `cfg.ga_caddy_enabled`.
- [x] 3.5 In `_reconcile_registry` (transport startup), re-register a Caddy server for every crew in `crews.json` with an allocated dashboard port; make re-registration idempotent (handle existing `@id`).
- [x] 3.6 Suppress `_start_dashboard_port_server` / the per-port uvicorn listener threads when `cfg.ga_caddy_enabled=True` — Caddy owns the port binding. Keep the port-pool allocation (transport still assigns the port and tells Caddy).
- [x] 3.7 Update `_handle_crew_dashboard_post`/`_handle_crew_dashboard_delete` to register/deregister a Caddy server (instead of a uvicorn thread) when Caddy is enabled.

## 4. Dashboard Auth Endpoints (forward_auth)

- [x] 4.1 Add an in-memory `_gs_session_store: dict[str, float]` (token → expiry); TTL default 24 h via `GA_CADDY_SESSION_TTL_SECS`.
- [x] 4.2 Implement `_handle_dashboard_login_post`: reads `ga_api_key`, constant-time compare with `GA_API_KEY`, on success issues `secrets.token_hex(32)` and returns `Set-Cookie: gs_session=<token>; HttpOnly; SameSite=Lax; Secure; Path=/` + 200; on failure 401.
- [x] 4.3 Implement `_handle_dashboard_auth`: validates `gs_session`, on 200 returns `X-Crew-Cookie: mc_token_5476=<crew cookie>` for the crew mapped from the incoming dashboard port; 401 otherwise.
- [x] 4.4 Implement `_handle_login_ui`: serves the minimal HTML form (no auth), honours `?next=` for post-login redirect.
- [x] 4.5 Register `/dashboard-login`, `/dashboard-auth`, `/login-ui` as public routes (served before `BearerAuthMiddleware`'s key check) and add them to the main Caddy server config.
- [x] 4.6 Add a `dashboard_auth` rate limiter (e.g. `GA_RATE_LIMIT_DASHBOARD_AUTH=60:60`) or exempt these routes deliberately.
- [ ] 4.7 Document the `basicauth` and `caddy-security` (OIDC/OAuth2, via `xcaddy`) alternatives as config-only swaps in `docs/caddy.md`.

## 5. install.sh

- [x] 5.1 Add `GA_CADDY_ENABLED`, `GA_CADDY_TLS_MODE`, `GA_CADDY_DOMAIN`, `GA_CADDY_PORT`, `GA_CADDY_HTTP_PORT` to the built-in defaults block.
- [x] 5.2 Add flag parsing for Caddy-specific CLI flags (e.g. `--caddy-domain`, `--caddy-tls-mode`).
- [x] 5.3 Generate `${DATA_DIR}/caddy/initial-config.json` (main server: MCP/file routes with Bearer matcher, health, dashboard-auth endpoints; TLS stanza parameterised by `GA_CADDY_TLS_MODE` — internal/tailscale/acme/off; no per-crew servers).
- [x] 5.4 Add the `ga-caddy` service stanza to the compose template (conditional on `GA_CADDY_ENABLED=true`): `caddy:2` image; bind 443/80 **and the dashboard port range**; inject `GA_API_KEY` env; mount `initial-config.json` (ro) and `ga-caddy-data`; `caddy run --config ... --resume`.
- [x] 5.5 **Move the dashboard port-range binding off `ga-transport`** when `GA_CADDY_ENABLED=true` (Caddy owns those ports; binding on both is a conflict).
- [x] 5.6 Add the `ga-caddy-data` named volume to the compose volumes section when Caddy is enabled.
- [x] 5.7 When `GA_CADDY_TLS_MODE=internal`, print the Caddy root CA cert path and a `caddy trust` instruction in the post-install output.
- [x] 5.8 Add a `ga-caddy` health check to the post-install probe.

## 6. ghostship CLI

- [x] 6.1 Surface the Caddy root CA cert path in `ghostship status` output when `GA_CADDY_TLS_MODE=internal`.

## 7. dashboard_url in launch and crews

- [x] 7.1 When `cfg.ga_caddy_enabled`, `launch()` returns `dashboard_url = https://{host}:{port}/` (HTTPS via Caddy; same per-port shape, TLS scheme).
- [x] 7.2 Update `crews()` to return the Caddy HTTPS per-port `dashboard_url` when Caddy is enabled, and the plain-HTTP per-port URL otherwise.

## 8. Tests

- [ ] 8.1 Unit tests for `_caddy_register_crew`/`_caddy_deregister_crew`: mock the Caddy admin API, assert the server JSON (listen port, forward_auth, upstream), assert 404-on-deregister handled gracefully.
- [ ] 8.2 Unit tests for `_handle_dashboard_login_post`: valid key → 200 + Set-Cookie; invalid → 401.
- [ ] 8.3 Unit tests for `_handle_dashboard_auth`: valid token → 200 + `X-Crew-Cookie`; expired/missing → 401; correct crew resolved from the incoming port.
- [ ] 8.4 Unit tests asserting per-port uvicorn listeners are NOT started when `GA_CADDY_ENABLED=True`, and ARE started when False.
- [ ] 8.5 Update `launch`/`nuke` tests to assert Caddy register/deregister when Caddy enabled.
- [ ] 8.6 Integration smoke test: start `ga-caddy` + `ga-transport`; `launch` a crew; assert `GET /config/id/crew-{id}` exists and the dashboard port serves HTTPS; assert an unauthenticated `/mcp` is 401 at Caddy; `nuke` and assert the server is gone.

## 9. Documentation and Release Notes

- [ ] 9.1 Create `docs/caddy.md`: overview, the single port-based routing model, the four TLS modes (internal/tailscale/acme/off with when-to-use), the `forward_auth` auth flow, the `basicauth`/`caddy-security` SSO upgrade path, and the vm23 "retire host Caddy" note.
- [ ] 9.2 Update `docs/dashboard-proxy.md`: Caddy-mode section, **breaking-change note** (clean cutover, Caddy binds the ports, no coexistence), updated Security section (dashboard ports now auth-gated via forward_auth).
- [ ] 9.3 Update `docs/auth.md`: `gs_session` cookie lifecycle, `/dashboard-login`, `/dashboard-auth`, edge Bearer enforcement for `/mcp` + `/files`, the auth-posture table (Caddy on vs off).
- [ ] 9.4 Update `docs/configuration.md`: all `GA_CADDY_*` vars, four TLS modes, internal-CA trust step, interaction with `GA_DASHBOARD_PORT_ENABLED`.
- [ ] 9.5 Add a release-notes entry: `GA_CADDY_ENABLED=true` is a **breaking** cutover — Caddy binds the dashboard ports, vm23 host Caddy is retired, no coexistence window.
