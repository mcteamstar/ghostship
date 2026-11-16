# Spec Delta

## MODIFIED Requirements

### Requirement: Crew creation via launch
The system SHALL create an isolated crew container with a dedicated workspace volume and a dedicated home volume when `launch` is called with a valid, unique `crew_id`. The container image and manifest path SHALL be resolved from the crew registry using the canonical `comp` argument. The legacy `composition` argument remains an accepted alias during the rollback window. If both arguments are present, `comp` SHALL be authoritative; when the values differ, the system SHALL use `comp` and log a warning naming both values. If only `composition` is present, its value SHALL be used. If neither is present, the existing `"spec-ops"` default SHALL be applied. At launch time, the system SHALL read the `org.ghostship.version` OCI label from the crew container and store it in the registry as `crew_image_version`. The `launch` tool SHALL refuse to create a new crew when the number of registered crews (running + stopped) is at or above `GA_MAX_CREWS` (default: 20). The error message SHALL distinguish between the total-registered limit and the active-running limit.

`launch` gains a `dashboard` parameter (default `null`). When `dashboard=true`, `launch` allocates a port from the configured range, registers it with Portal, stores `dashboard_port` in the registry, and returns `dashboard_url` in the response. When `dashboard=false` or when `dashboard=null` (default) and `GA_DASHBOARD_DEFAULT` is unset or false, no port is allocated and `dashboard_url` is `null`.

When `GA_DASHBOARD_DEFAULT=true`, every `launch()` call behaves as if `dashboard=True` was passed unless the caller explicitly passes `dashboard=False`. The caller-supplied value always wins over the site default. The resolution rule is: `effective_dashboard = dashboard if dashboard is not None else GA_DASHBOARD_DEFAULT`.

#### Scenario: First launch for a new crew_id
- **WHEN** `launch` is called with a `crew_id` that has no existing registry entry and the registered crew count is below `GA_MAX_CREWS`
- **THEN** a new crew container and volumes are created and the crew is registered as "running"

#### Scenario: Launch with canonical comp parameter
- **WHEN** `launch` is called with a valid `crew_id` and canonical `comp="worker"`
- **THEN** the system resolves the `"worker"` crew type's image and manifest from the registry and uses them instead of the hardcoded defaults

#### Scenario: Launch with unknown comp
- **WHEN** `launch` is called with a legacy `composition` value not found in the loaded crew registry
- **THEN** the system returns an error listing the available crew types and creates no container

#### Scenario: Launch with legacy composition alias
- **WHEN** `launch` is called with a valid `crew_id` and `composition="worker"` but no `comp`
- **THEN** the system resolves the `"worker"` crew entry and uses its image and manifest

#### Scenario: Matching comp and composition values
- **WHEN** `launch` is called with `comp="worker"` and `composition="worker"`
- **THEN** the system resolves the `"worker"` crew entry and uses its image and manifest

#### Scenario: Conflicting comp and composition values
- **WHEN** `launch` is called with `comp="worker"` and `composition="spec-ops"`
- **THEN** the system uses `comp` (`"worker"`), resolves that crew entry, and logs a warning naming both values

#### Scenario: Neither comp argument is provided
- **WHEN** `launch` is called without `comp` or `composition`
- **THEN** the crew is created using the default `"spec-ops"` registry entry

#### Scenario: Invalid crew_id
- **WHEN** `launch` is called with a `crew_id` that does not match lowercase alphanumeric/hyphen, 1-50 characters
- **THEN** the system returns an error and creates no container, volume, or registry entry

#### Scenario: Duplicate crew_id
- **WHEN** `launch` is called with a `crew_id` that already has a registry entry not in `auth_required` status
- **THEN** the system returns an error instructing the caller to nuke the existing crew first

#### Scenario: Max registered crews reached
- **WHEN** `launch` is called while the number of registered crews is already at or above `GA_MAX_CREWS`
- **THEN** `launch` returns an error indicating the registered crew limit has been reached and instructing the operator to nuke a crew first

#### Scenario: Gateway does not become ready
- **WHEN** the newly started crew container's gateway does not respond within 30 seconds
- **THEN** the system tears down the container and both volumes it just created and returns an error, leaving no partial registry entry

#### Scenario: Launch image without version label
- **WHEN** `launch` is called and the resolved container image does not carry the `org.ghostship.version` label
- **THEN** the system stores `"unknown"` as `crew_image_version` in the registry and proceeds normally — the missing label is not a launch failure

#### Scenario: GA_DASHBOARD_DEFAULT=true, no explicit dashboard arg
- **WHEN** `GA_DASHBOARD_DEFAULT=true` is configured and `launch(crew_id)` is called with no `dashboard` argument
- **THEN** a dashboard port is allocated and `dashboard_url` is non-null in the response, as if `dashboard=True` had been passed

#### Scenario: GA_DASHBOARD_DEFAULT=true, explicit dashboard=False overrides
- **WHEN** `GA_DASHBOARD_DEFAULT=true` is configured and `launch(crew_id, dashboard=False)` is called
- **THEN** no dashboard is allocated and `dashboard_url` is null — the explicit `False` wins over the site default

#### Scenario: GA_DASHBOARD_DEFAULT unset or false, no explicit arg — unchanged behaviour
- **WHEN** `GA_DASHBOARD_DEFAULT` is unset or `false` and `launch(crew_id)` is called with no `dashboard` argument
- **THEN** no dashboard is allocated and `dashboard_url` is null — existing default behaviour preserved

