## 1. AsyncMiddlewareBase

- [x] 1.1 Add `AsyncMiddlewareBase` to `transport/auth.py` with `__init__(self, app)`, `__call__` (non-HTTP pass-through + `handle_http` dispatch), and abstract `handle_http`
- [x] 1.2 Refactor `TransportSecretMiddleware` to inherit from `AsyncMiddlewareBase`; move HTTP logic into `handle_http`
- [x] 1.3 Refactor `RateLimitMiddleware` to inherit from `AsyncMiddlewareBase`; move HTTP logic into `handle_http`
- [x] 1.4 Refactor `BearerAuthMiddleware` to inherit from `AsyncMiddlewareBase`; extract `_dispatch_public_route`, `_dispatch_file`, `_dispatch_authenticated` sub-methods from `__call__`; implement `handle_http` as the dispatcher (note: `_dispatch_websocket` is not needed — `AsyncMiddlewareBase.__call__` handles non-HTTP pass-through before `handle_http` is called)
- [x] 1.5 Run tests; confirm all middleware tests pass

## 2. DashboardGate

- [x] 2.1 Create `transport/dashboard.py` and define `DashboardGate` class with `__init__(self, session_ttl_secs, api_key, tls_mode)` initialising `_throttle`, `_sessions`, `_csrf_token`, `_port_crew: dict[int, str]`, and `_port_crew_lock`; import `security` here (not in `caddy.py` — that module's acyclic constraint excludes security imports)
- [x] 2.2 Move `_handle_dashboard_login_post`, `_handle_dashboard_auth`, `_handle_dashboard_logout_post`, and `_handle_login_get` (login UI) into `DashboardGate` as instance methods (`handle_login_post`, `handle_auth`, `handle_logout_post`, `handle_login_get`)
- [x] 2.3 Add `register_port(crew_id, port)` and `release_port(port)` instance methods to `DashboardGate` for the `_dashboard_port_crew` mutations currently in `server.py` and `lifecycle.py`
- [x] 2.4 In `server.py`, remove the five dashboard module-level globals; construct one `DashboardGate` instance after config/secrets load; update `public_routes` and `routes` dicts to reference its bound methods
- [x] 2.5 Update `lifecycle.py` calls that mutate `_dashboard_port_crew` to use the `DashboardGate` instance (pass it as a parameter to the relevant lifecycle functions)
- [x] 2.6 Run tests; confirm all dashboard auth and session tests pass

## 3. CaddyPortal

- [ ] 3.1 Define `CaddyPortal` class in `transport/caddy.py` with `__init__(self, port, api_key, port_range_start, port_range_size)` absorbing the `PORT`, `GA_API_KEY`, `GA_DASHBOARD_PORT_RANGE_START`, `GA_DASHBOARD_PORT_RANGE_SIZE` module globals
- [ ] 3.2 Expose `allocate_port()`, `release_port(port)`, `register_crew(crew_id, port, crew_cookie)`, and `deregister_crew(crew_id)` as instance methods wrapping the existing module-level functions
- [ ] 3.3 In `server.py`, remove the four `_caddy.X = Y` post-import mutation lines; construct `CaddyPortal(port=PORT, api_key=GA_API_KEY, ...)` after secrets load
- [ ] 3.4 Update all `_caddy._allocate_dashboard_port()`, `_caddy._release_dashboard_port()`, `_caddy._caddy_register_crew()`, `_caddy._caddy_deregister_crew()` call sites in `server.py` and `lifecycle.py` to use the `CaddyPortal` instance methods
- [ ] 3.5 Keep the module-level functions in `caddy.py` as thin wrappers or remove them once all call sites are updated; update the module docstring to describe the new pattern
- [ ] 3.6 Run tests; confirm all launch, nuke, and dashboard proxy tests pass

## 4. captain() Decomposition

- [ ] 4.1 Extract the `action == "order"` path (~150 lines) from `captain()` into a `_captain_do_order(crew_id, message, template, change_name, cron, interval, timezone, fire_immediately, model) -> dict` module-level function in `server.py`
- [ ] 4.2 Extract the `action == "stop"` path into `_captain_do_stop(crew_id) -> dict`
- [ ] 4.3 Extract the `action == "status"` path into `_captain_do_status(crew_id) -> dict`
- [ ] 4.4 Rewrite `captain()` as a ~20-line dispatcher: validate inputs, select action, delegate to the appropriate helper
- [ ] 4.5 Run tests; confirm all captain tests pass

## 5. Final Verification

- [ ] 5.1 Run the full test suite; confirm zero regressions
- [ ] 5.2 Verify `server.py` no longer contains `_dashboard_throttle`, `_gs_sessions`, `_dashboard_csrf_token`, `_dashboard_port_crew` module-level names or `_caddy.X = Y` post-import mutations
- [ ] 5.3 Verify `BearerAuthMiddleware.__call__` (or `handle_http`) is no longer a monolith — each sub-method is independently readable
