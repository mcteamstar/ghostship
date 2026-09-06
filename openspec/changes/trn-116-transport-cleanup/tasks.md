## 1. Dead Code Removal

- [x] 1.1 Remove the body of `_inject_git_identity` in `transport/lifecycle.py`, leaving only the function signature; replace its call site in `_finish_crew_setup` with a comment noting that git identity vars are injected at container-create time; remove the two `_inject_git_identity` imports in `transport/server.py` (lines ~541 and ~597)
- [x] 1.2 Remove the `KIROCREW_ALLOW_UNSANDBOXED: "1"` env injection from the `launch` handler in `transport/server.py`; add a comment referencing `sandbox: off` config as the replacement
- [x] 1.3 Run `tests/run.sh` (or equivalent) and confirm all existing tests pass

## 2. Auth Header Parse Deduplication

- [x] 2.1 Add a `_parse_bearer_token(header_value: str) -> str | None` helper in `transport/server.py` that extracts the token from an `Authorization: Bearer <token>` header, returns `None` on any malformed input
- [x] 2.2 Replace the two inline `[:7].lower() == "bearer "` checks in `BearerAuthMiddleware` and any other call sites with calls to `_parse_bearer_token`
- [x] 2.3 Run the test suite and confirm all existing tests pass

## 3. `_crew_api_with_recovery` Phase Extraction

- [x] 3.1 Extract the 503 retry block from `_crew_api_with_recovery` into `_phase0_transient_503(crew, method, path, **kw)` in `transport/lifecycle.py`
- [x] 3.2 Extract the 400/401/403 cookie-refresh block into `_phase1_stale_cookie(crew, crew_id, method, path, **kw)` in `transport/lifecycle.py`
- [x] 3.3 Extract the connection-error restart block into `_phase2_dead_gateway(crew, crew_id, method, path, **kw)` in `transport/lifecycle.py`
- [x] 3.4 Update `_crew_api_with_recovery` to delegate to the three helpers; add a one-line phase-label comment at each delegation point
- [x] 3.5 Run the test suite and confirm all existing tests pass; update any mock paths that now target the phase helpers

## 4. `_initiate_login` Internal Documentation

- [x] 4.1 Add section-header comments to `_initiate_login` in `transport/server.py` (matching the style used in `_crew_api_with_recovery`): `# ── Phase: acquire lock / TOCTOU guard`, `# ── Phase: start login container`, `# ── Phase: wait for kiro-cli`, `# ── Phase: PTY exec + prompt loop`, `# ── Phase: drain thread + finalise`
- [x] 4.2 Add an inline comment explaining the 45-second deadline and the reason for the `select`-based read loop (non-blocking PTY drain to avoid blocking the event loop)
- [x] 4.3 No behaviour change — verify by running the test suite

## 5. Schedule/Idle Monitor Documentation

- [x] 5.1 Add section-header comments to `_schedule_monitor` in `transport/lifecycle.py` documenting the loop interval (`_SCHEDULE_MONITOR_INTERVAL`), the exit condition (daemon thread — exits with the process), and the three actions it may take per cycle
- [x] 5.2 Add equivalent section-header comments to `_idle_monitor` documenting its interval, exit condition, and the idle-stop threshold
- [x] 5.3 No behaviour change — verify by running the test suite

## 6. Extract `transport/auth.py`

- [x] 6.1 Create `transport/auth.py` containing `TransportSecretMiddleware`, `RateLimitMiddleware`, `BearerAuthMiddleware`, `SecurityHeadersMiddleware`, `_parse_bearer_token`, and their private helpers (`_parse_rate_limit_var`, `_build_rate_limiters`, `_request_source`)
- [x] 6.2 Update `transport/server.py` to import the middleware classes from `auth` (flat) or `transport.auth` (package) using the dual-path `try/except` pattern
- [x] 6.3 Update `tests/unit/test_server.py` mock paths for any middleware internals that moved
- [x] 6.4 Run the full test suite and confirm all tests pass

## 7. Extract `transport/caddy.py`

- [x] 7.1 Create `transport/caddy.py` containing `_caddy_admin_url`, `_allocate_dashboard_port`, `_release_dashboard_port`, `_caddy_register_crew`, `_caddy_deregister_crew`; note that `_allocate_dashboard_port` and `_release_dashboard_port` must be called while holding `_registry_lock` (imported from `lifecycle`)
- [x] 7.2 Update `transport/server.py` to import these helpers from `caddy` / `transport.caddy` using the dual-path pattern
- [x] 7.3 Update `tests/unit/test_server.py` mock paths for any Caddy helpers that moved
- [x] 7.4 Run the full test suite and confirm all tests pass

## 8. Extract `transport/monitors.py`

- [ ] 8.1 Create `transport/monitors.py` containing `_schedule_monitor`, `_idle_monitor`, `_cron_activity_since`, `_cron_has_enabled_job`; import `_crew_api_with_recovery`, `_ensure_crew_running`, and related constants from `lifecycle` / `transport.lifecycle` using the dual-path pattern
- [ ] 8.2 Update `transport/lifecycle.py` to remove these functions and import `start_monitors` (or equivalent) from `monitors` / `transport.monitors`
- [ ] 8.3 Update `tests/unit/test_lifecycle.py` mock paths for monitor functions that moved
- [ ] 8.4 Run the full test suite and confirm all tests pass

## 9. Test Coverage Gaps

- [ ] 9.1 Add tests in `tests/unit/test_server.py` for `_handle_crew_ui_proxy` when the upstream crew gateway returns a non-2xx response (e.g. 502, 503) — assert the error is surfaced correctly to the caller
- [ ] 9.2 Add tests for dashboard URL construction when Caddy TLS is off — assert the URL uses `http://` and the direct port rather than the Caddy-proxied HTTPS URL
- [ ] 9.3 Run the full test suite and confirm all tests pass including the new ones
