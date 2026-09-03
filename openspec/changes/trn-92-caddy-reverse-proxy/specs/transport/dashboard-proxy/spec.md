## MODIFIED Requirements

### Requirement: Dashboard routing mode
When `GA_CADDY_ENABLED=true`, the transport SHALL route dashboard requests through Caddy path-prefix proxying (`/crews/{id}/ui/` on the single Caddy-managed port) instead of allocating per-crew ports from the `GA_DASHBOARD_PORT_RANGE`. The per-port daemon-thread model (`GA_DASHBOARD_PORT_ENABLED`) SHALL default to `false` when `GA_CADDY_ENABLED=true` and SHALL still be activatable by explicitly setting `GA_DASHBOARD_PORT_ENABLED=true` (for mixed or transition deployments).

#### Scenario: Caddy-mode dashboard access
- **WHEN** `GA_CADDY_ENABLED=true` and a crew named `alpha` is launched
- **THEN** the crew's dashboard is accessible at `https://<host>/crews/alpha/ui/`
- **THEN** no per-port listener is started for the crew
- **THEN** `launch` returns a `dashboard_url` of the form `https://<host>/crews/alpha/ui/`

#### Scenario: Per-port mode unaffected when Caddy disabled
- **WHEN** `GA_CADDY_ENABLED=false` and `GA_DASHBOARD_PORT_ENABLED=true`
- **THEN** dashboard access via per-port proxies works exactly as before TRN-92
- **THEN** `launch(dashboard=True)` allocates a port and starts a daemon-thread proxy

#### Scenario: dashboard_url shape reflects active mode
- **WHEN** `GA_CADDY_ENABLED=true` and crew `alpha` is launched
- **THEN** `crews()` returns `dashboard_url: "https://<host>/crews/alpha/ui/"` for that crew
- **WHEN** `GA_CADDY_ENABLED=false` and crew `beta` has a port allocated
- **THEN** `crews()` returns `dashboard_url: "http://localhost:<port>/"` for `beta`
