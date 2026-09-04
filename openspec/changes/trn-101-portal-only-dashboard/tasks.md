## 1. Reject dashboard=True when Portside disabled

- [x] 1.1 In `launch()` (transport/server.py), when `dashboard=True` and `GA_PORTAL_ENABLED=false`, return an MCP error: `"dashboard access requires GA_PORTAL_ENABLED=true; re-run install.sh and re-launch any existing dashboard crews — see docs/dashboard-proxy.md"` before any port allocation
- [x] 1.2 Add unit test: `launch(dashboard=True)` with Portside disabled returns the expected error and allocates no port

## 2. Remove per-port uvicorn proxy machinery

- [x] 2.1 Delete `_start_dashboard_port_server(port, crew_id, app)` and `_stop_dashboard_port_server(port)`
- [x] 2.2 Delete `_dashboard_app` module-level variable and the startup assignment at line ~4430
- [x] 2.3 Remove the startup loop that re-starts per-port listeners on container restart (~line 4438)
- [x] 2.4 In `_handle_crew_dashboard_post`: remove the uvicorn `_start_dashboard_port_server` call; keep port allocation and `_caddy_register_crew`; add the Portside-disabled error guard (task 1.1 covers `launch`, this covers the HTTP path)
- [x] 2.5 In `_handle_crew_dashboard_delete`: remove `_stop_dashboard_port_server` call; keep `_caddy_deregister_crew`
- [x] 2.6 In `nuke()`: remove `_stop_dashboard_port_server` call (Portside deregister is already there)

## 3. Remove GA_DASHBOARD_PORT_ENABLED config

- [x] 3.1 Remove `ga_dashboard_port_enabled` field from `Config` dataclass in `transport/config.py`
- [x] 3.2 Remove `GA_DASHBOARD_PORT_ENABLED` from `from_env()` reader
- [x] 3.3 Remove `GA_DASHBOARD_PORT_ENABLED = cfg.ga_dashboard_port_enabled` module-level assignment in `server.py` and all its uses
- [x] 3.4 Remove `GA_DASHBOARD_PORT_ENABLED` from `config/ghostship.conf.example` (with a migration comment: use `GA_PORTAL_ENABLED=true` instead)
- [x] 3.5 Remove from `docs/configuration.md`

## 4. Documentation

- [x] 4.1 Update `docs/dashboard-proxy.md`: remove the "Portside disabled" section; document `GA_PORTAL_ENABLED=true` as the requirement; add the migration steps from design.md
- [x] 4.2 Add a breaking-change note in `CHANGELOG.md`
- [x] 4.3 Update the `launch` MCP tool docstring: note that `dashboard=True` requires `GA_PORTAL_ENABLED=true` and will return an error otherwise

## 5. Tests

- [x] 5.1 Remove or update tests that test the per-port uvicorn proxy path (TRN-80 era tests that patch `_start_dashboard_port_server` or `_dashboard_app`)
- [x] 5.2 Update the `GA_DASHBOARD_PORT_ENABLED` config sync test to reflect its removal
- [x] 5.3 Run `tests/run.sh --unit` and confirm all tests pass
