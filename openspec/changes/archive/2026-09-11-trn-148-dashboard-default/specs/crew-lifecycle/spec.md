# Crew Lifecycle — Delta Spec (trn-148-dashboard-default)

Updates to the `crew-lifecycle` capability.

## MODIFIED Requirements

### Requirement: Crew launch

`launch` gains a `dashboard` parameter (default `false`). When `dashboard=true` and `GA_DASHBOARD_PORT_ENABLED=true`, `launch` allocates a port from the configured range, starts a transport-side listener, injects the session cookie and CORS origins, stores `dashboard_port` in the registry, and returns `dashboard_url` in the response. When `dashboard=false` (default), no port is allocated and `dashboard_url` is `null`.

The effective `dashboard` value SHALL be resolved as `dashboard OR GA_DASHBOARD_DEFAULT`. When `GA_DASHBOARD_DEFAULT=true`, every `launch()` call behaves as if `dashboard=True` was passed, unless the caller explicitly passes `dashboard=False`. The caller-supplied value always wins.

#### Scenario: GA_DASHBOARD_DEFAULT=true, no explicit dashboard arg

- **WHEN** `GA_DASHBOARD_DEFAULT=true` is configured and `launch(crew_id)` is called with no `dashboard` argument
- **THEN** a dashboard port is allocated and `dashboard_url` is non-null in the response, as if `dashboard=True` had been passed

#### Scenario: GA_DASHBOARD_DEFAULT=true, explicit dashboard=False overrides

- **WHEN** `GA_DASHBOARD_DEFAULT=true` is configured and `launch(crew_id, dashboard=False)` is called
- **THEN** no dashboard is allocated and `dashboard_url` is null — the explicit `False` wins over the site default

#### Scenario: GA_DASHBOARD_DEFAULT unset or false, no explicit arg — unchanged behaviour

- **WHEN** `GA_DASHBOARD_DEFAULT` is unset or `false` and `launch(crew_id)` is called with no `dashboard` argument
- **THEN** no dashboard is allocated and `dashboard_url` is null — existing default behaviour preserved
