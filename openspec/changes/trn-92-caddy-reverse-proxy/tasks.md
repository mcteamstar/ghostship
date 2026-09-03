## 1. Prerequisites and Dependency Verification

- [ ] 1.1 Confirm with the upstream KiroCrew team whether `ghcr.io/kirodotdev/kirocrew:0.4.0` supports a configurable SPA base URL (e.g. `KIROCREW_BASE_URL`) for path-prefix deployments (Open Question 2 in design.md). Block task 5.x if not supported.
- [ ] 1.2 Test that the existing `vm23` Caddy instance does not bind port 443/80 on the same host interface as the intended `ga-caddy` deployment, or document the recommended topology for vm23 operators (Open Question 1).

## 2. Config and Environment

- [ ] 2.1 Add new fields to `transport/config.py`: `ga_caddy_enabled`, `ga_caddy_admin_url`, `ga_caddy_tls_mode`, `ga_caddy_domain`, `ga_caddy_port`, `ga_caddy_http_port`; add corresponding `from_env()` reads with documented defaults.
- [ ] 2.2 Add `GA_CADDY_*` variable documentation to `config/ghostship.conf.example` with comments matching the existing style.
- [ ] 2.3 Add `GA_CADDY_*` variable documentation to `docs/configuration.md`.

## 3. Caddy Admin API Integration in Transport

- [ ] 3.1 Implement `_caddy_admin_url()` helper in `transport/server.py` that reads `cfg.ga_caddy_admin_url`.
- [ ] 3.2 Implement `_caddy_register_crew(crew_id, cookie_value)`: builds the route JSON object (with `@id: "crew-{crew_id}"`, path matcher, `forward_auth` sub-handler, and `reverse_proxy` sub-handler with cookie injection), POSTs to `/config/apps/http/servers/ga/routes/.` on the Caddy admin API, retries 3× with backoff, logs warning on failure (does not raise).
- [ ] 3.3 Implement `_caddy_deregister_crew(crew_id)`: calls `DELETE /config/id/crew-{crew_id}`, handles 404 gracefully, logs warning on other failure.
- [ ] 3.4 Call `_caddy_register_crew` at the end of `_finish_crew_setup` (inside `_registry_lock`, after cookie is minted) when `cfg.ga_caddy_enabled`.
- [ ] 3.5 Call `_caddy_deregister_crew` in `nuke` (before registry removal) when `cfg.ga_caddy_enabled`.
- [ ] 3.6 In `_reconcile_registry` (called at transport startup), re-register routes for all crews in `crews.json` that lack a Caddy route (handles restart-after-volume-recreation scenario).
- [ ] 3.7 Suppress `_start_dashboard_port_server` call in `launch` when `cfg.ga_caddy_enabled=True` and `cfg.ga_dashboard_port_enabled` is not explicitly overridden.
- [ ] 3.8 Update `_handle_crew_dashboard_post` and `_handle_crew_dashboard_delete` to return 409 with a descriptive error when `GA_CADDY_ENABLED=True` (per-port dashboard allocation is a no-op in Caddy mode).

## 4. Dashboard Auth Endpoints

- [ ] 4.1 Add in-memory `_gs_session_store: dict[str, float]` (token → expiry timestamp) to `server.py`; default TTL 24 h configurable via `GA_CADDY_SESSION_TTL_SECS`.
- [ ] 4.2 Implement `_handle_dashboard_login_post(request)`: reads `ga_api_key` from JSON body, constant-time compare with `GA_API_KEY`, on success generates a `secrets.token_hex(32)` token, stores it with expiry, returns `Set-Cookie: gs_session=<token>; HttpOnly; SameSite=Lax; Path=/` + 200; on failure returns 401.
- [ ] 4.3 Implement `_handle_dashboard_auth(request)`: reads `Cookie: gs_session=<token>`, looks up in `_gs_session_store`, returns 200 + `X-Crew-Cookie` header (value: `mc_token_5476=<crew_cookie>` for the matched crew) on valid token, 401 on invalid/missing/expired. Determine crew from request path or a `X-Original-URI` header forwarded by Caddy's `forward_auth`.
- [ ] 4.4 Implement `_handle_login_ui(request)`: serves minimal HTML form that POST to `/dashboard-login`, reads `?next=` param for post-login redirect, no auth required.
- [ ] 4.5 Register all three endpoints (`/dashboard-login`, `/dashboard-auth`, `/login-ui`) in `BearerAuthMiddleware._public_routes` (no API-key auth, served before auth check).
- [ ] 4.6 Add the three endpoints to `RateLimitMiddleware._EXEMPT` or add a `dashboard_auth` limiter with a tight limit (e.g. `GA_RATE_LIMIT_DASHBOARD_AUTH=60:60`).

## 5. Caddy `dashboard_url` in `launch` and `crews`

- [ ] 5.1 When `cfg.ga_caddy_enabled`, derive `dashboard_url` in `launch()` as `https://{cfg.ga_caddy_domain}/crews/{crew_id}/ui/` (or `http://localhost:{cfg.ga_caddy_port}/crews/{crew_id}/ui/` when domain is empty/TLS off).
- [ ] 5.2 Update `crews()` to return the Caddy-derived `dashboard_url` for each crew when Caddy is enabled, falling back to the per-port URL when not.

## 6. install.sh

- [ ] 6.1 Add `GA_CADDY_ENABLED`, `GA_CADDY_TLS_MODE`, `GA_CADDY_DOMAIN`, `GA_CADDY_PORT`, `GA_CADDY_HTTP_PORT` to the built-in defaults block.
- [ ] 6.2 Add flag parsing for any Caddy-specific CLI flags (e.g. `--caddy-domain`).
- [ ] 6.3 Add a section that generates `${DATA_DIR}/caddy/initial-config.json` based on `GA_CADDY_TLS_MODE`, `GA_CADDY_DOMAIN`, `GA_CADDY_PORT`. Use the skeleton from `design.md`. Parameterise TLS stanza by mode (internal/acme/off).
- [ ] 6.4 Add `ga-caddy` service stanza to compose.yml template (conditional on `GA_CADDY_ENABLED=true`): `caddy:2` image, port bindings, `ga-net`, volume mounts for `initial-config.json` (ro) and `ga-caddy-data`, `caddy run --config /config/initial-config.json --resume` command.
- [ ] 6.5 Add `ga-caddy-data` named volume to compose.yml volumes section when Caddy is enabled.
- [ ] 6.6 Suppress `GA_DASHBOARD_PORT_RANGE_START-END` port range from `ga-transport` stanza when `GA_CADDY_ENABLED=true`.
- [ ] 6.7 When `GA_CADDY_TLS_MODE=internal`, print post-install instructions for running `caddy trust` to add the local CA root.
- [ ] 6.8 Add a health check for the `ga-caddy` container in the post-install check (probe `http://localhost:${GA_CADDY_HTTP_PORT}/health` or the configured port).

## 7. Tests

- [ ] 7.1 Unit tests for `_caddy_register_crew` and `_caddy_deregister_crew`: mock the Caddy admin HTTP endpoint, assert correct JSON payload, assert 404 on deregister is handled gracefully.
- [ ] 7.2 Unit tests for `_handle_dashboard_login_post`: valid key → 200 + Set-Cookie; invalid key → 401.
- [ ] 7.3 Unit tests for `_handle_dashboard_auth`: valid token → 200 + X-Crew-Cookie; expired token → 401; missing cookie → 401.
- [ ] 7.4 Update `launch` and `nuke` unit tests to assert Caddy register/deregister calls when `GA_CADDY_ENABLED=True`.
- [ ] 7.5 Integration smoke test (manual or CI): start `ga-caddy` + `ga-transport` containers, call `launch`, verify `/config/id/crew-{id}` exists on Caddy admin API; call `nuke`, verify it's gone.

## 8. Documentation

- [ ] 8.1 Create `docs/caddy.md`: overview, when to use it, quick-start for local (`internal` TLS) and remote (`acme`) modes, Tailscale notes, vm23/existing-Caddy topology note.
- [ ] 8.2 Update `docs/dashboard-proxy.md`: add Caddy-mode section, cross-reference per-port mode as the fallback; update Security section to reflect cookie-gated login.
- [ ] 8.3 Update `docs/auth.md`: describe `gs_session` cookie, `POST /dashboard-login`, `GET /dashboard-auth` endpoints.
- [ ] 8.4 Update `docs/configuration.md`: document all `GA_CADDY_*` variables with defaults, accepted values, and interaction with `GA_DASHBOARD_PORT_ENABLED`.
- [ ] 8.5 Update `README.md` quick-start to mention `GA_CADDY_ENABLED=true` as the recommended path for remote/TLS deployments.
