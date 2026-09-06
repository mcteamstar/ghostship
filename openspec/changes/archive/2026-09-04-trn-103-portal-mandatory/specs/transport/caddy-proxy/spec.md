## MODIFIED Requirements

### Requirement: `ga-portal` is always present

`ga-portal` SHALL always be included in the generated `compose.yml` and started by `install.sh`. There is no opt-out flag. The `GA_PORTAL_ENABLED` environment variable is removed and SHALL NOT be read or honoured.

#### Scenario: Install always starts ga-portal

- **WHEN** `install.sh` runs
- **THEN** `compose.yml` always contains a `ga-portal` service
- **THEN** `ga-portal` is started alongside `ga-transport`

### Requirement: Dashboard access is unconditional

`launch(dashboard=True)` SHALL allocate a port and register with `ga-portal` without checking a `GA_PORTAL_ENABLED` flag. The dashboard is always available on deployments where `ga-portal` is healthy.

#### Scenario: Dashboard launch always succeeds when portal is healthy

- **WHEN** `launch(dashboard=True)` is called and `ga-portal` is running
- **THEN** a port is allocated, `_caddy_register_crew` is called, and `dashboard_url` is returned
- **WHEN** `ga-portal` is not running or Caddy registration fails
- **THEN** `launch` logs a warning but still returns `dashboard_url` (registration failure is non-fatal)

## REMOVED Requirements

### Requirement: GA_PORTAL_ENABLED opt-in flag

**Reason**: Removed in TRN-103. `ga-portal` is now a mandatory component. The opt-out mode (`GA_PORTAL_ENABLED=false`) is not supported.

**Migration**: Re-run `install.sh`. `ga-portal` will be started automatically. Configure `GA_PORTAL_TLS_MODE` as needed (default: `internal`).
