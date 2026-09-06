## MODIFIED Requirements

### Requirement: Dashboard routing mode
Dashboard routing SHALL remain port-based in all cases — each crew UI is served at a dedicated port from the `GA_DASHBOARD_PORT_RANGE` (default 64058–64107), because the KiroCrew SPA requires a root origin. Path-prefix routing (`/crews/{id}/ui/`) and subdomain routing SHALL NOT be used. When `GA_CADDY_ENABLED=true`, Caddy SHALL bind those per-crew ports (adding TLS and `forward_auth` on each) and proxy to `http://gs-{id}:5476/`, and the transport SHALL NOT start its per-port uvicorn listener threads. When `GA_CADDY_ENABLED=false`, the transport SHALL bind and serve those ports itself, exactly as before this change. There is no mode in which both bind the same port simultaneously — enabling Caddy is a clean cutover.

#### Scenario: Caddy-mode dashboard access
- **WHEN** `GA_CADDY_ENABLED=true` and crew `alpha` is launched with `dashboard=True`
- **THEN** the crew dashboard is accessible over HTTPS at the crew's dedicated port (e.g. `https://<host>:64058/`)
- **THEN** Caddy binds that port and the transport starts no per-port listener for the crew
- **THEN** `launch` returns a `dashboard_url` of the form `https://<host>:<port>/`

#### Scenario: Per-port transport mode when Caddy disabled
- **WHEN** `GA_CADDY_ENABLED=false` and `GA_DASHBOARD_PORT_ENABLED=true`
- **THEN** the transport binds the port and runs its per-port uvicorn proxy exactly as before TRN-92
- **THEN** `launch(dashboard=True)` allocates a port and starts a daemon-thread proxy

#### Scenario: dashboard_url shape reflects the active terminator
- **WHEN** `GA_CADDY_ENABLED=true` and crew `alpha` has port 64058 allocated
- **THEN** `crews()` returns `dashboard_url: "https://<host>:64058/"` for `alpha`
- **WHEN** `GA_CADDY_ENABLED=false` and crew `beta` has port 64059 allocated
- **THEN** `crews()` returns `dashboard_url: "http://localhost:64059/"` for `beta`
