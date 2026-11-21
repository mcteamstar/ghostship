# crew-lifecycle/provisioning Specification

## Purpose

Defines how Transport provisions, configures and removes durable crew workspaces.

## Requirements

### Requirement: Crew creation via launch
`launch` SHALL create an isolated crew with workspace/home volumes for a valid unique ID, resolve `comp` (legacy `composition` alias; `comp` wins conflicts with a warning; default `spec-ops`), store the image version, and enforce `GA_MAX_CREWS` (default 100) across registered crews with distinct total/active-limit errors. Dashboard defaulting follows the explicit argument then `GA_DASHBOARD_DEFAULT`; enabled launches return a URL.

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

#### Scenario: Dashboard port is registered with Portal
- **WHEN** `launch` is called with `dashboard=True`
- **THEN** the system allocates and stores a UI port, registers the crew with Portal, and returns its `dashboard_url`

### Requirement: Crew teardown via nuke
`nuke` SHALL require confirmation, attempt to remove the container and both volumes, and remove the registry entry after cleanup attempts. For an assigned dashboard, it SHALL remove the Portal registration and release the port. Documentation SHALL describe it as destructive permanent teardown, not routine cleanup. Resource failures SHALL be identified and return a cleanup-failure status.

#### Scenario: Nuke without confirmation
- **WHEN** `nuke` is called for an existing `crew_id` without `confirm=True`
- **THEN** the system returns the container name, both volume names, and the count of currently active (non-done) tasks, and removes nothing

#### Scenario: Nuke with confirmation
- **WHEN** `nuke` is called for an existing `crew_id` with `confirm=True` and all Podman resource cleanup succeeds
- **THEN** the system attempts to stop and remove the crew's container, remove its workspace and home volumes, and remove the crew from the registry
- **THEN** the response reports successful teardown

#### Scenario: Nuke reports incomplete Podman cleanup
- **WHEN** `nuke` is called with `confirm=True` and one or more container or volume removal operations fail
- **THEN** the system continues attempting cleanup of the remaining resources and removes the crew from the registry after those attempts
- **THEN** the response reports cleanup failure and identifies every resource whose cleanup failed
- **THEN** the response does not claim an unqualified successful teardown

#### Scenario: Stop failure followed by successful removal is complete
- **WHEN** stopping the container fails but force-removal of the container and removal of both volumes succeed
- **THEN** `nuke` reports successful teardown because no Podman resource remains

#### Scenario: Nuke an unknown crew
- **WHEN** `nuke` is called with a `crew_id` that has no registry entry
- **THEN** the system returns an error and takes no action

#### Scenario: Nuke tool docstring excludes cleanup alias
- **WHEN** a user or agent reads the `nuke` tool's docstring or alias list
- **THEN** "clean up" SHALL NOT appear as an alias, and the docstring SHALL note that idle crews stop and restart automatically — `nuke` is for when the operator wants to discard the workspace entirely

#### Scenario: Nuke is not depicted as the lifecycle endpoint
- **WHEN** a user reads the README's SDD lifecycle diagram
- **THEN** the diagram SHALL NOT show `nuke` as the final step; the diagram SHALL end at `evac` or an equivalent non-destructive operation, and a note below SHALL explain that `nuke` is for intentional workspace destruction, not routine cleanup

### Requirement: Nuke dry-run reports scheduled jobs
The `nuke` dry-run response (called without `confirm=True`) SHALL include the count and names of all scheduled jobs registered for the crew in the transport registry, so the operator can see what recurring work will be discarded before confirming teardown.

#### Scenario: Crew has scheduled jobs
- **WHEN** `nuke` is called for a crew that has one or more entries in its transport registry `schedules` list, without `confirm=True`
- **THEN** the response includes `scheduled_jobs: <count>` (integer) and `scheduled_job_names: [<name>, ...]` (list of job name strings) alongside the existing `active_tasks` and `volumes` fields

#### Scenario: Crew has no scheduled jobs
- **WHEN** `nuke` is called for a crew that has no entries in its transport registry `schedules` list, without `confirm=True`
- **THEN** the response includes `scheduled_jobs: 0` and `scheduled_job_names: []`

### Requirement: Confirmed nuke clears scheduled jobs before container teardown
Before teardown, confirmed nuke SHALL issue `DELETE /api/crons/<job_id>` for each registered schedule. Cancellation failures SHALL be logged at WARNING but SHALL NOT prevent teardown; remove the crew and all schedule entries afterward regardless.

#### Scenario: Confirmed nuke with running container and active schedules
- **WHEN** `nuke(confirm=True)` is called for a crew that is running and has two scheduled jobs in the transport registry
- **THEN** the system issues `DELETE /api/crons/<job_id>` for each job to the gateway, then stops and removes the container, removes both volumes, and removes the crew registry entry (including all schedule entries)

#### Scenario: Confirmed nuke with stopped container and active schedules
- **WHEN** `nuke(confirm=True)` is called for a crew whose container is stopped and that has scheduled jobs in the transport registry
- **THEN** the gateway cancellation is best-effort (errors are logged at WARNING level), the container removal and registry deletion proceed regardless, and the registry entry (including all schedule entries) is removed

#### Scenario: Confirmed nuke cancellation failure does not block teardown
- **WHEN** `nuke(confirm=True)` is called and the `DELETE /api/crons/<job_id>` request fails for one or more jobs due to a gateway error
- **THEN** the failure is logged at `WARNING` level and `nuke` continues to tear down the container, remove volumes, and remove the registry entry

#### Scenario: Confirmed nuke with no scheduled jobs
- **WHEN** `nuke(confirm=True)` is called for a crew that has no entries in its transport registry `schedules` list
- **THEN** no cron cancellation requests are issued and the teardown proceeds as before

### Requirement: Crew setup completion is all-or-nothing

The system SHALL mark a crew running only after required setup succeeds and SHALL clean up on any required-step failure. Auth injection is verified by exit code, not output text.

#### Scenario: Successful setup

- **WHEN** all setup steps succeed
- **THEN** the crew is marked "running", and the Admiral public key has been
  present in the container since it first started

### Requirement: Admiral signing key is ready before crew setup
Before first startup, transport SHALL generate the Ed25519 keypair, persist and `fsync` the private seed host-side, and attach the public key as a Podman secret. Setup SHALL NOT inject the private key.

#### Scenario: Admiral secret present before post-restart gateway

- **WHEN** the transport has completed auth injection and the pre-restart gateway
  wait, and then restarts the container
- **THEN** the Admiral key material the crew needs is already in place, because
  the public key was attached to the `container_create` spec as a read-only
  Podman secret and has been readable at `/run/secrets/.admiral_public_key`
  since the container first started. No setup step writes it, and the guarantee
  now holds from container creation rather than from just before the restart

#### Scenario: No setup step writes the Admiral key into the container

- **WHEN** crew setup runs to completion
- **THEN** no `container_exec` call writes Admiral key material, and the private
  seed exists only host-side

### Requirement: Setup failures prevent crew registration
Required setup failures SHALL clean up the crew and SHALL NOT mark it running.

#### Scenario: Cookie mint fails

- **WHEN** every step up to and including cookie minting succeeds except
  `_mint_cookie`
- **THEN** the crew is cleaned up and `launch` returns an error

#### Scenario: Auth injection failure is detected
- **WHEN** the auth injection command exits with a non-zero exit code
- **THEN** the system treats the injection as failed, does not proceed with the remaining setup steps, and tears down the partially-created crew

#### Scenario: Auth injection output is not used as a success signal
- **WHEN** the auth injection command exits with a non-zero exit code but its output contains the word "injected"
- **THEN** the system treats the injection as failed, not as successful

### Requirement: Setup steps follow dependency order
Setup SHALL follow: pre-restart gateway wait, auth, policy-key generation, config patch (`agent` from `GA_CREW_AGENT`, default `kiro`), restart, post-restart gateway wait, copy agents/skills/steering, seed OpenSpec, inject policy, wait for built-in agents, patch model files, mint cookie, then record image version and registry. Agent files SHALL be written after gateway readiness and before it serves requests because the runtime directory is read-only.

#### Scenario: Agent files written before runtime write-protection
- **WHEN** `_copy_agents` is called during crew setup
- **THEN** the agent JSON files are written to `KIRO_AGENTS_DIR` during the
  post-restart gateway startup window, before KiroCrew 0.5.0 makes that
  directory write-protected at runtime

### Requirement: Crew and resource naming convention

The system SHALL name every crew-scoped Podman resource with a gs- prefix derived from the crew_id, kept entirely separate from the ga- prefix used for fixed Ghost Academy infrastructure (ga-transport, ga-portside, ga-starboard) — so a crew_id can never collide with a fixed infrastructure name, regardless of what the caller picks.

#### Scenario: Resource names for a crew
- **WHEN** a crew is created for crew_id
- **THEN** its container is named gs-<crew_id>, its workspace volume gs-vol-<crew_id>, its home volume gs-home-<crew_id>, and it joins the shared ga-starboard network

#### Scenario: crew_id matching an infra name
- **WHEN** a crew is created with crew_id equal to transport or starboard
- **THEN** the resulting crew container does not collide with fixed ga-transport or the ga-starboard network because ga- and gs- are different prefixes

### Requirement: Documentation frames crews as persistent workspaces
The system's documentation SHALL frame crews as persistent workspaces that survive across multiple changes, and SHALL distinguish the automatic idle-stop/restart mechanism (transparent, reversible, no data loss) from `nuke` (explicit, permanent, workspace-destroying).

#### Scenario: README intro describes crew persistence
- **WHEN** a user reads the README introduction
- **THEN** the text SHALL describe crews as persistent workspaces that can be reused across multiple features, not as disposable entities that are "banished when done"

#### Scenario: Architecture doc distinguishes idle-stop from nuke
- **WHEN** a user reads the crew lifecycle section of `docs/architecture.md`
- **THEN** the document SHALL include a note distinguishing idle-stop (automatic, transparent, reversible) from nuke (explicit, permanent, workspace-destroying), and SHALL identify idle-stop as the normal resource management path

### Requirement: Crew container environment includes KIROCREW_CREW_ID

The crew container environment MUST set `KIROCREW_CREW_ID` to its registry ID/container suffix, in the same `container_env` as `KIROCREW_CORS_ORIGINS`. Raven's internal stop URL construction depends on it.

#### Scenario: Crew container receives KIROCREW_CREW_ID

- **WHEN** a crew is launched with crew_id "test-crew"
- **THEN** KIROCREW_CREW_ID is set to "test-crew" in the container environment

#### Scenario: Raven self-cancel constructs correct URL

- **GIVEN** KIROCREW_CREW_ID is set to "test-crew" in the container env
- **WHEN** Raven executes the self-cancel script
- **THEN** the curl URL is `http://ga-transport:64057/crews/test-crew/captain/stop`
- **AND** the request reaches the captain/stop endpoint handler
