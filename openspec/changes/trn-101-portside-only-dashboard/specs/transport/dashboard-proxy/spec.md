## MODIFIED Requirements

### Requirement: Dashboard routing mode

Dashboard routing SHALL remain port-based — each crew launched with `dashboard=True` gets a dedicated port from the `GA_DASHBOARD_PORT_RANGE`. `GA_PORTSIDE_ENABLED=true` is **required** for dashboard access; the transport SHALL NOT start per-port proxy listeners. When Portside is disabled, `launch(dashboard=True)` SHALL be rejected.

#### Scenario: Dashboard launch requires Portside

- **WHEN** `GA_PORTSIDE_ENABLED=false` and `launch(dashboard=True)` is called
- **THEN** the call returns an error: `"dashboard access requires GA_PORTSIDE_ENABLED=true; re-run install.sh and re-launch any existing dashboard crews — see docs/dashboard-proxy.md"`
- **THEN** no port is allocated and `dashboard_url` is not set

#### Scenario: Caddy-mode dashboard access

- **WHEN** `GA_PORTSIDE_ENABLED=true` and crew `alpha` is launched with `dashboard=True`
- **THEN** the crew dashboard is accessible over the configured TLS scheme at the crew's dedicated port (e.g. `https://<host>:64058/`)
- **THEN** Portside (`ga-portside`) binds that port; the transport starts no per-port listener
- **THEN** `launch` returns a `dashboard_url` of the form `<scheme>://<host>:<port>/`

#### Scenario: dashboard_url null when Portside disabled

- **WHEN** `GA_PORTSIDE_ENABLED=false` and `launch(dashboard=False)` is called (or `dashboard` omitted)
- **THEN** `dashboard_url` is `null` and no port is allocated

## REMOVED Requirements

### Requirement: Per-port transport proxy when Caddy disabled

**Reason**: Removed in TRN-101. The transport's per-port uvicorn proxy threads were a workaround replaced by `ga-portside`. Dashboard proxying is Portside's responsibility. Operators must enable `GA_PORTSIDE_ENABLED=true` to use dashboard access.

**Migration**: Set `GA_PORTSIDE_ENABLED=true` in `ghostship.conf` and re-run `install.sh`. See `docs/dashboard-proxy.md` for the Portside setup guide.
