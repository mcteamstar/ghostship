# Crew Lifecycle Specification

## Purpose

Manage the creation and teardown of isolated KiroCrew "crew" containers on demand, so agent work happens in dedicated, disposable environments rather than a single shared or permanently running instance.

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

### Requirement: REST API to retrofit or remove a dashboard

`POST /crews/{crew_id}/dashboard` SHALL allocate a UI port and register it with Portal, idempotently reusing an active dashboard. `DELETE` SHALL remove the Portal registration, release the port, and return null, including when already inactive. Both endpoints SHALL honor `GA_API_KEY` authentication.

#### Scenario: POST /dashboard on a running crew
- **WHEN** `POST /crews/my-crew/dashboard` is called for a crew without a `dashboard_port`
- **THEN** a port is allocated, a listener is started, and the response includes `dashboard_url`

#### Scenario: DELETE /dashboard on a running crew
- **WHEN** `DELETE /crews/my-crew/dashboard` is called
- **THEN** the listener is stopped, the port released, and `dashboard_url` becomes null

#### Scenario: DELETE /dashboard when no dashboard is active
- **WHEN** `DELETE /crews/my-crew/dashboard` is called and the crew has no `dashboard_port`
- **THEN** the response returns `{"dashboard_url": null}` as a no-op — no error

#### Scenario: POST /dashboard when already active
- **WHEN** `POST /crews/my-crew/dashboard` is called and the crew already has a `dashboard_port`
- **THEN** the existing `dashboard_url` is returned with no change

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

### Requirement: Waiter timeout is sufficient for worst-case leader restart

The waiter `event.wait(timeout=...)` in `transport/launcher.py` SHALL be set to at
least 150 seconds. The leader restart path under memory pressure can exceed 120
seconds; a shorter timeout causes waiters to raise a spurious 502 while the leader
is still making progress.

#### Scenario: Waiter does not time out during normal leader restart
- **WHEN** a leader restart takes up to 120 seconds to complete
- **THEN** waiters do not raise a timeout error before the leader signals completion

#### Scenario: Waiter timeout is >= 150 seconds
- **WHEN** `transport/launcher.py` is read
- **THEN** the `event.wait(timeout=...)` value is >= 150

### Requirement: Concurrent restart outcome reads are generation-stable

The transport SHALL track per-crew `_startup_generation` under `_startup_events_lock`. A restart leader increments it; waiters capture it before waiting and re-read it afterward. If it changed, they SHALL NOT read the old outcome and SHALL retry `_ensure_crew_running` or report a timeout.

#### Scenario: Two waiters, leader fails — both see the failure

- **WHEN** two callers arrive after a leader has been elected for `crew_id`
- **AND** the leader's restart fails
- **THEN** both waiters read `success=False` from `_crew_restart_outcomes` and raise the stored exception
- This is the existing TRN-152 behavior; the generation counter SHALL NOT break it.

#### Scenario: Third caller arrives mid-cycle, pops the event before waiters read

- **GIVEN** callers A (leader) and B (waiter) are mid-restart for `crew_id`
- **WHEN** a third caller C arrives immediately after A fires the event and pops `_startup_events[crew_id]`, and C becomes the new leader for a fresh restart cycle
- **THEN** B, waking from `event.wait()`, observes that `_startup_generation[crew_id]` has changed from the value it captured before waiting
- **AND** B does NOT read `_crew_restart_outcomes` for A's cycle
- **AND** B raises a RuntimeError or retries, rather than proceeding against a crew that may or may not be running

#### Scenario: Normal two-caller case is unaffected

- **WHEN** exactly two callers arrive (leader + one waiter) and the leader succeeds
- **THEN** the waiter reads `success=True` from `_crew_restart_outcomes` and returns normally; the generation counter is incremented but does not change between the waiter's capture and its post-wait read

### Requirement: Headless crew config overrides
At launch, transport SHALL deep-merge spec-ops overrides into `config.local.json` across agent, stt, session, telemetry, and top-level sections. Defaults disable STT, eager spawn, beacon telemetry, and auto-update; set session timeout to 300s and RSS cap to 2000MB. The patcher SHALL accept full-section overrides. It SHALL omit knowledge settings: KiroCrew 0.9.0 has separate opt-in ingest flags defaulting off, guarded by CI.

#### Scenario: Fresh crew launch has headless overrides applied

- **GIVEN** a crew is being launched for the first time
- **WHEN** `_patch_crew_config` is called on the new container
- **THEN** `config.local.json` contains `stt.enabled = false`, `session.eager_spawn = false`, `session.timeout_secs = 300`, `session.watchdog_rss_max_mb = 2000`, `telemetry.beacon_enabled = false`, and `auto_update = false`

#### Scenario: Knowledge auto-ingest is disabled after headless overrides applied
- **WHEN** `_patch_crew_config` is called on a new crew container running KiroCrew 0.9.0+
- **THEN** `config.local.json` contains no `knowledge` section written by ghostship
- **AND** knowledge auto-ingest is disabled by the verified upstream default (opt-in)
- **AND** no knowledge auto-ingest path (artifact watcher, agent auto-add-documents, folder ingestion) is active

#### Scenario: full_overrides declares no knowledge section
- **WHEN** `_patch_crew_config` builds the `full_overrides` dict
- **THEN** `full_overrides` contains no `knowledge` key
- **AND** no inert/dead `knowledge.auto_ingest` pin is written (no such upstream key exists to pin)

#### Scenario: Upstream default flip is caught by the regression test
- **GIVEN** the disabled posture relies on the upstream default rather than a config pin
- **WHEN** a future KiroCrew version changes a knowledge ingest toggle's built-in default to `true`
- **THEN** `tests/unit/test_trn223_knowledge_autoingest.py` fails in CI, surfacing the change for an explicit re-decision
- **AND** the posture is not silently flipped on inside crew containers without notice

#### Scenario: Upgrade from KiroCrew 0.8.x to 0.9.0 is a no-op for ingest
- **WHEN** an existing crew's base image is bumped from `0.8.x` to `0.9.0+`
- **THEN** the crew's auto-ingest behaviour is identical before and after the upgrade (disabled in both versions)

#### Scenario: Knowledge section can still deep-merge if an operator opts in
- **WHEN** `full_overrides` includes `{"knowledge": {"auto_ingest_artifacts": true}}`
- **THEN** `config.local.json` contains a top-level `knowledge` object with that key via the existing `_deep_merge()` logic — no patcher change is required
- **AND** existing top-level sections (`agent`, `session`, `telemetry`, `agents`) are preserved

#### Scenario: Idle crew RSS is below 200 MB after headless overrides

- **GIVEN** a crew has been launched with headless overrides applied
- **WHEN** no task has been dispatched for more than 60 seconds
- **THEN** the crew container RSS is below 200 MB (gateway process only; no pre-spawned session process)

#### Scenario: Session process spawns on first dispatch and is reaped after timeout

- **GIVEN** a crew is idle with `session.eager_spawn = false` and `session.timeout_secs = 300`
- **WHEN** a task is dispatched via `dispatch`
- **THEN** a `kiro-cli-chat` session process is spawned within 5 seconds of task start
- **AND WHEN** the task completes and 300 seconds elapse with no further dispatch
- **THEN** the session process is reaped and the crew RSS returns to below 200 MB

#### Scenario: patch_crew_config.py deep-merges non-agent sections

- **GIVEN** a full config override dict including `stt`, `session`, and `telemetry` sections is passed to `patch_crew_config.py`
- **WHEN** the script runs inside the container
- **THEN** `config.local.json` contains each section at the correct top-level key, deep-merged with any existing content
- **AND** the existing `agent` section overrides are preserved unchanged

### Requirement: Crew and resource naming convention

The system SHALL name every crew-scoped Podman resource with a gs- prefix derived from the crew_id, kept entirely separate from the ga- prefix used for fixed Ghost Academy infrastructure (ga-transport, ga-portside, ga-starboard) — so a crew_id can never collide with a fixed infrastructure name, regardless of what the caller picks.

#### Scenario: Resource names for a crew
- **WHEN** a crew is created for crew_id
- **THEN** its container is named gs-<crew_id>, its workspace volume gs-vol-<crew_id>, its home volume gs-home-<crew_id>, and it joins the shared ga-starboard network

#### Scenario: crew_id matching an infra name
- **WHEN** a crew is created with crew_id equal to transport or starboard
- **THEN** the resulting crew container does not collide with fixed ga-transport or the ga-starboard network because ga- and gs- are different prefixes

### Requirement: Bounded gateway session-token lifetime
The system SHALL mint gateway session tokens used to establish crew session cookies with a configurable lifetime, defaulting to 24 hours rather than one year, and SHALL use that setting consistently during initial setup, stopped-crew recovery, and transport-startup reconciliation.

#### Scenario: Default gateway token lifetime
- **WHEN** a crew is set up or its session is refreshed without an explicit gateway token lifetime configuration
- **THEN** the transport requests a gateway token with a 24-hour lifetime before exchanging it for the stored session cookie

#### Scenario: Configured gateway token lifetime
- **WHEN** the transport is given a valid gateway token lifetime configuration
- **THEN** initial setup and every later cookie refresh use that configured lifetime

#### Scenario: File-transfer URL lifetime remains independent
- **WHEN** a gateway session token lifetime is changed
- **THEN** the existing `GA_FILE_TTL_SECS` expiry for `evac` and `supply` URLs remains unchanged

### Requirement: Documentation frames crews as persistent workspaces
The system's documentation SHALL frame crews as persistent workspaces that survive across multiple changes, and SHALL distinguish the automatic idle-stop/restart mechanism (transparent, reversible, no data loss) from `nuke` (explicit, permanent, workspace-destroying).

#### Scenario: README intro describes crew persistence
- **WHEN** a user reads the README introduction
- **THEN** the text SHALL describe crews as persistent workspaces that can be reused across multiple features, not as disposable entities that are "banished when done"

#### Scenario: Architecture doc distinguishes idle-stop from nuke
- **WHEN** a user reads the crew lifecycle section of `docs/architecture.md`
- **THEN** the document SHALL include a note distinguishing idle-stop (automatic, transparent, reversible) from nuke (explicit, permanent, workspace-destroying), and SHALL identify idle-stop as the normal resource management path

### Requirement: CSRF/cookie auto-recovery on stale credentials
The transport SHALL detect stale session credentials when `_crew_api` receives a 400, 401, or 403 response from a running container, transparently re-mint the session cookie via `container_exec`, update the registry, and retry the original request exactly once — without user intervention. If the re-mint fails, the transport SHALL escalate to a full container restart via `_ensure_crew_running`.

#### Scenario: Stale cookie triggers transparent refresh
- **WHEN** `_crew_api` sends a request to a running crew container and receives a 400, 401, or 403 HTTP response
- **THEN** the transport mints a new session cookie, updates the registry, and retries the original request with the fresh cookie

#### Scenario: Successful retry after cookie refresh
- **WHEN** the retried request with the fresh cookie succeeds
- **THEN** the original caller receives the successful response as if the stale-cookie episode never happened

#### Scenario: Cookie re-mint fails
- **WHEN** the transport detects a stale credential and the `_mint_cookie` call returns no valid cookie
- **THEN** the transport escalates to a full container restart via `_ensure_crew_running` before retrying

#### Scenario: Retry limit prevents infinite loops
- **WHEN** a request has already been retried once after credential refresh (or once after container restart)
- **THEN** the transport does not attempt further retries and surfaces the error to the caller

### Requirement: Gateway liveness probe
The transport SHALL distinguish between "container stopped" and "container running but gateway unresponsive" by performing a lightweight HTTP probe against the gateway URL before treating a running container as healthy. If the probe fails on a running container, the transport SHALL treat it as a gateway crash and execute the recovery path.

#### Scenario: Probe succeeds on a running container
- **WHEN** `_ensure_crew_running` finds the container running and the gateway liveness probe succeeds
- **THEN** the container is treated as healthy with no further action

#### Scenario: Probe fails on a running container
- **WHEN** `_ensure_crew_running` finds the container running but the gateway liveness probe fails
- **THEN** the transport restarts the container, waits for the gateway, refreshes the session cookie, and updates the registry

#### Scenario: Probe timeout is bounded
- **WHEN** the gateway liveness probe is issued
- **THEN** it SHALL complete within 5 seconds so a hung gateway does not block the caller indefinitely

### Requirement: Retry with backoff on transient failures
The transport SHALL wrap `_crew_api` calls in a retry layer that attempts recovery at most once per failure class. After two consecutive failures, the transport SHALL stop retrying and surface a clear error.

#### Scenario: Connection error triggers restart-then-retry
- **WHEN** `_crew_api` raises a connection error and the container is running
- **THEN** the transport restarts the gateway via `_ensure_crew_running` and retries the request once

#### Scenario: Two consecutive failures surface an error
- **WHEN** the retry after recovery also fails
- **THEN** the transport does not attempt further recovery and raises a descriptive error to the caller

### Requirement: User-facing error messages on recovery failure
The transport SHALL return a human-readable error message when all recovery attempts are exhausted, stating the crew identifier, what was attempted, and a suggested next action — not a raw HTTP status code or Python traceback.

#### Scenario: Recovery exhausted error format
- **WHEN** a `_crew_api` call fails after all retry/recovery attempts
- **THEN** the error message includes the crew identifier, states that the transport attempted recovery, and suggests the caller retry momentarily or check the crew's status

#### Scenario: Stale-cookie recovery failure surfaces actionable message
- **WHEN** an MCP tool call to a crew fails after the transport exhausted cookie-refresh and restart recovery
- **THEN** the MCP error response includes a message like "crew <crew_id> is unresponsive — the transport attempted recovery but the gateway did not come back. Try calling again in a moment or check crew status with crews()."

#### Scenario: Connection-error recovery failure surfaces actionable message
- **WHEN** an MCP tool call to a crew fails due to a connection error after the transport attempted a restart
- **THEN** the MCP error response includes a message identifying the crew, stating restart was attempted, and suggesting the caller retry or inspect the crew

#### Scenario: Error does not leak internal details
- **WHEN** a recovery-failure error is surfaced to the caller
- **THEN** the message does not include raw HTTP response bodies, Python stack traces, or internal container names beyond the crew_id

### Requirement: Gateway health field in crews() output
The `crews()` tool SHALL include a `gateway_healthy: bool` field in each crew entry, reflecting whether the gateway liveness probe succeeded at the time of the call.

#### Scenario: Healthy gateway
- **WHEN** `crews()` is called and a crew's container is running and its gateway responds to the liveness probe
- **THEN** that crew's entry includes `gateway_healthy: true`

#### Scenario: Unresponsive gateway
- **WHEN** `crews()` is called and a crew's container is running but its gateway does not respond to the liveness probe
- **THEN** that crew's entry includes `gateway_healthy: false`

#### Scenario: Stopped container
- **WHEN** `crews()` is called and a crew's container is stopped
- **THEN** that crew's entry includes `gateway_healthy: false`

### Requirement: Concurrent login guard is atomic
The system SHALL hold the login-pending lock across both the auth-file guard check and the _login_pending guard check, so that two concurrent POST /login requests cannot both pass both guards and start duplicate login containers.

#### Scenario: Concurrent login requests are serialised
- **WHEN** two POST /login requests arrive simultaneously and no login is in progress
- **THEN** exactly one proceeds to start a login container; the other receives a 409 response indicating a login is already in progress

#### Scenario: Sequential login check is consistent
- **WHEN** a POST /login request checks both the auth-file guard and the login-pending guard
- **THEN** both checks are evaluated while holding the same lock, so a concurrent request cannot slip through between the two checks

### Requirement: crews() includes crew image version
The `crews()` tool SHALL include a `crew_image_version` field in each crew entry, reflecting the version of the crew image that crew was built from. The value SHALL be sourced from the registry, populated at launch time.

#### Scenario: crews() shows version for a running crew
- **WHEN** `crews()` is called and a crew has `crew_image_version` stored in the registry
- **THEN** the crew entry includes `crew_image_version` with the stored semver string

#### Scenario: crews() for a crew launched before version tracking
- **WHEN** `crews()` is called and a crew's registry entry has no `crew_image_version` field
- **THEN** the crew entry includes `crew_image_version` set to `"unknown"`

### Requirement: Crew list response includes timing metadata

The `crews` tool response SHALL include `created_at` (ISO 8601 UTC, from the existing `crews.json` registry entry) and `last_task_at` (ISO 8601 UTC, the most recent time a task was dispatched on this crew) for each crew entry. `last_task_at` SHALL be `null` if no task has been dispatched on this crew.

#### Scenario: crews list includes created_at
- **WHEN** `crews` is called
- **THEN** each entry includes `created_at` derived from the registry

#### Scenario: crews list includes last_task_at after a dispatch
- **WHEN** at least one task has been dispatched on a crew and `crews` is called
- **THEN** that crew's entry includes `last_task_at` as an ISO 8601 UTC string

#### Scenario: crews list last_task_at is null for a newly launched crew
- **WHEN** a crew has been launched but no task has been dispatched
- **THEN** `last_task_at` is `null`

### Requirement: Pre-launch memory gate

Before waking a stopped crew, transport SHALL require headroom from Linux `MemAvailable` or Podman info elsewhere. It polls every five seconds until `GA_MIN_FREE_MEM_GB` (2.0 default) is met or `GA_MEMORY_WAIT_SECS` (60 default) expires; timeout or unknown memory fails closed with crew, available, and required values. Patch `spawn_min_memory_gb` from `GA_SPAWN_MIN_MEMORY_GB` (1.5 default).

#### Scenario: Linux admission uses MemAvailable
- **WHEN** a stopped crew container is being restarted on Linux and `/proc/meminfo` reports `MemAvailable` above `GA_MIN_FREE_MEM_GB`
- **THEN** the container starts immediately even if `MemFree` is below the threshold

#### Scenario: Memory available immediately
- **WHEN** a stopped crew container is being restarted AND available memory exceeds `GA_MIN_FREE_MEM_GB`
- **THEN** the container starts immediately with no delay

#### Scenario: Memory becomes available within timeout
- **WHEN** a stopped crew container is being restarted AND available memory is below `GA_MIN_FREE_MEM_GB` AND memory becomes available within `GA_MEMORY_WAIT_SECS`
- **THEN** the container starts after the wait, with no error

#### Scenario: Memory does not free within timeout
- **WHEN** a stopped crew container is being restarted AND available memory remains below `GA_MIN_FREE_MEM_GB` for the full `GA_MEMORY_WAIT_SECS` duration
- **THEN** the system returns an error: `"Insufficient available memory to start crew <id>: <N>GB available, <T>GB required. Retry in a moment."`

#### Scenario: Linux available memory cannot be determined
- **WHEN** the transport cannot read or parse `MemAvailable` from `/proc/meminfo`
- **THEN** it does not start the crew and returns a clear error that available memory could not be determined

#### Scenario: Non-Linux memory source
- **WHEN** a stopped crew container is being restarted on a non-Linux host
- **THEN** the transport uses the available-memory value reported by Podman info

#### Scenario: Memory gate disabled
- **WHEN** `GA_MIN_FREE_MEM_GB` is set to `0`
- **THEN** the pre-launch memory check is skipped entirely and the container starts unconditionally

### Requirement: Configurable spawn_min_memory_gb patch

The `_patch_crew_config` function SHALL write `GA_SPAWN_MIN_MEMORY_GB` (default
1.5) into the crew's `spawn_min_memory_gb` config field instead of the
hardcoded value `0`.

The `spawn_min_memory_gb` field SHALL be written as a native config file entry
(not via a runtime workaround) because KiroCrew 0.5.0 fixes the loader that
previously ignored this field in config files.

#### Scenario: Default spawn threshold
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is not set
- **THEN** `spawn_min_memory_gb` is patched to `1.5`

#### Scenario: Custom spawn threshold
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is set to `2.0`
- **THEN** `spawn_min_memory_gb` is patched to `2.0`

#### Scenario: spawn_min_memory_gb zero is a valid disable sentinel
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is set to `0`
- **THEN** `spawn_min_memory_gb` is patched to `0` in the config, disabling
  the spawn memory gate inside the crew

#### Scenario: spawn_min_memory_gb written via config file, not workaround
- **WHEN** a stopped crew container is restarted via `_ensure_crew_running`
- **THEN** the stop/start/patch/stop/start workaround sequence is NOT executed;
  instead a single `_patch_crew_config` + restart sequence is used, because
  KiroCrew 0.5.0 reads `spawn_min_memory_gb` from the config file correctly

### Requirement: Configurable resource pressure thresholds

The `_patch_crew_config` function SHALL read `GA_RESOURCE_PRESSURE_GB` (default
2.0) and `GA_RESOURCE_CRITICAL_GB` (default 1.0) from the environment and patch
them into the crew's config, replacing the current hardcoded `0` values.

#### Scenario: Default pressure thresholds
- **WHEN** neither `GA_RESOURCE_PRESSURE_GB` nor `GA_RESOURCE_CRITICAL_GB` is set
- **THEN** `resource_pressure_gb` is patched to `2.0` and `resource_critical_gb` is patched to `1.0`

#### Scenario: Custom pressure thresholds
- **WHEN** `GA_RESOURCE_PRESSURE_GB=3.0` and `GA_RESOURCE_CRITICAL_GB=1.5`
- **THEN** those values are written into the crew config

### Requirement: Crew configuration supports operator-tunable task timeout

At launch, transport SHALL write task timeout and turn limits from `GA_SUBAGENT_TIMEOUT_SECS` (default 3600) and `GA_SUBAGENT_MAX_TURNS` (default 200). `docs/configuration.md` SHALL document both settings.

#### Scenario: Operator sets custom timeout

- **WHEN** the transport is started with `GA_SUBAGENT_TIMEOUT_SECS=7200`
- **THEN** every new crew's `config.local.json` contains `subagent_timeout_secs: 7200`

#### Scenario: Default timeout applied when env var absent

- **WHEN** the transport is started without `GA_SUBAGENT_TIMEOUT_SECS` set
- **THEN** every new crew's `config.local.json` contains `subagent_timeout_secs: 3600`

#### Scenario: Operator sets custom turn limit

- **WHEN** the transport is started with `GA_SUBAGENT_MAX_TURNS=300`
- **THEN** every new crew's `config.local.json` contains `subagent_max_turns: 300`

### Requirement: Config patch applied on reconcile restart

When a stopped crew is started on demand after a transport restart, the system SHALL apply pending configuration patches, including `spawn_min_memory_gb`, before marking it running, using the normal recovery path. Startup reconciliation SHALL NOT start a stopped container solely to apply patches.

#### Scenario: Stopped crew restored after transport restart
- **WHEN** an operation or due work wakes a stopped crew after transport restart
- **THEN** `_patch_crew_config` is called before the crew is marked running

#### Scenario: Config patch idempotent on repeated restarts
- **WHEN** the same crew is woken after repeated transport restarts
- **THEN** each demand-driven recovery applies `_patch_crew_config` without error and reflects current transport defaults

### Requirement: Registry reconciliation is idempotent

`_reconcile_registry` SHALL produce the same registry state whether
called once or multiple times in succession for the same set of running
containers.

#### Scenario: Reconcile called twice without container changes
- **WHEN** `_reconcile_registry` is called a second time while all
  previously-reconciled crews are already running
- **THEN** no container is restarted again and registry state is unchanged

#### Scenario: Reconcile tolerates containers already running
- **WHEN** a crew container is already in running state at reconcile time
- **THEN** `_reconcile_registry` does not restart it and does not error

### Requirement: Registry file written with restricted permissions
The system SHALL write `crews.json` with file permissions `0o600` (owner read/write only), ensuring the registry is not readable by other local users on the host.

#### Scenario: Registry written with 0o600 permissions
- **WHEN** `_save_registry` writes `crews.json`
- **THEN** the resulting file has permissions `0o600`

#### Scenario: Existing registry file permissions corrected on write
- **WHEN** `_save_registry` is called on a host where `crews.json` already exists with broader permissions
- **THEN** after the write the file has permissions `0o600`

### Requirement: dangerously_skip_permissions usage is annotated
Any call site in the codebase that passes `dangerously_skip_permissions=True` SHALL include an inline comment explaining why the permission bypass is required and what threat model constraint that implies.

#### Scenario: dangerously_skip_permissions call site has explanatory comment
- **WHEN** a developer reads the code at the `dangerously_skip_permissions=True` call site
- **THEN** the comment explains the purpose of the bypass and the security implication of enabling it

### Requirement: Threat model for admiral secret delivery is documented
The system's documentation SHALL describe the threat model for the admiral secret: why it must not reside in a file readable by agent processes, what privilege boundary the env-var delivery provides, and the residual risk (host-level access bypasses all container-side controls).

#### Scenario: Documentation covers admiral secret threat model
- **WHEN** a user or operator reads the security section of `docs/auth.md`
- **THEN** they find an explanation of why the admiral secret must not be in a world-readable file, what the delivery mechanism protects against, and what it does not protect against

### Requirement: Configurable model default patch
`_patch_crew_config` SHALL set `agent.default_model` from non-empty `KC_MODEL_DEFAULT` (otherwise omit it) and set `agent` from `GA_CREW_AGENT` (default `kiro`). Document the default. Effective model precedence is `KC_MODEL_OVERRIDE`, per-agent model, `KC_MODEL_DEFAULT`, then KiroCrew's built-in default.

#### Scenario: KC_MODEL_DEFAULT set
- **WHEN** the transport is started with `KC_MODEL_DEFAULT=anthropic/claude-sonnet-4`
- **THEN** every new crew's `config.local.json` contains `default_model: "anthropic/claude-sonnet-4"` inside the `agent` block

#### Scenario: KC_MODEL_DEFAULT unset
- **WHEN** the transport is started without `KC_MODEL_DEFAULT`
- **THEN** `_patch_crew_config` does NOT write a `default_model` field into `config.local.json`, leaving KiroCrew's built-in default unchanged

#### Scenario: agent field required in config
- **WHEN** `_patch_crew_config` writes `config.local.json`
- **THEN** the `agent` config block includes an `agent` field set to the value
  of `GA_CREW_AGENT` (default `"kiro"`), satisfying KiroCrew 0.4.0's
  required-field check

#### Scenario: GA_CREW_AGENT unset uses default
- **WHEN** `GA_CREW_AGENT` is not set
- **THEN** `_patch_crew_config` writes `"agent": "kiro"` into the config block

#### Scenario: KC_MODEL_DEFAULT does not affect per-agent pins
- **WHEN** `KC_MODEL_DEFAULT` is set and an agent JSON contains a non-empty `"model"` field (and `KC_MODEL_OVERRIDE` is unset)
- **THEN** that agent continues to use its own pinned model; `KC_MODEL_DEFAULT` only applies to agents whose effective model would otherwise fall through to the KiroCrew built-in

#### Scenario: KC_MODEL_OVERRIDE beats KC_MODEL_DEFAULT
- **WHEN** both `KC_MODEL_OVERRIDE` and `KC_MODEL_DEFAULT` are set
- **THEN** `_patch_models` writes `KC_MODEL_OVERRIDE` into every agent JSON's `"model"` field, making `KC_MODEL_DEFAULT` irrelevant in practice (the per-agent field is now set, so the default is never reached)

### Requirement: Base image version

The transport SHALL use `ghcr.io/kirodotdev/kirocrew:0.6.0` as the default value of `KC_BASE_IMAGE` (both the `Config` dataclass field and the `from_env()` fallback). The version string SHALL appear in exactly two places in `transport/config.py` and nowhere else as a hardcoded literal.

#### Scenario: Default base image is 0.6.0
- **WHEN** `Config.from_env()` is called without `KC_BASE_IMAGE` set
- **THEN** `cfg.kc_base_image` is `"ghcr.io/kirodotdev/kirocrew:0.6.0"`

#### Scenario: KC_BASE_IMAGE override is respected
- **WHEN** `KC_BASE_IMAGE=ghcr.io/myorg/custom:latest` is set
- **THEN** `cfg.kc_base_image` is `"ghcr.io/myorg/custom:latest"`

### Requirement: Crew config patches sandbox=off for Podman rootless compatibility

`_patch_crew_config` SHALL set `agent.sandbox` to `off` to avoid unsupported inner namespace remounts under rootless Podman. The Podman container remains the OS isolation boundary.

#### Scenario: Crew spawns succeed on Podman rootless
- **WHEN** a crew is launched on a Podman rootless host (the standard ghostship deployment)
- **THEN** `config.local.json` contains `"sandbox": "off"` inside the `agent` block
- **AND** agent dispatches complete without `AcpRuntimeDead: process exited (rc=1)`

#### Scenario: Crew spawns succeed on Podman rootless with 0.6.0 image
- **WHEN** a crew is launched using `ghcr.io/kirodotdev/kirocrew:0.6.0` on a Podman rootless host
- **THEN** `config.local.json` contains `"sandbox": "off"` inside the `agent` block
- **AND** agent dispatches complete without `AcpRuntimeDead: process exited (rc=1)`

#### Scenario: sandbox=off does not affect authentication or governance
- **WHEN** `"sandbox": "off"` is patched into the crew config
- **THEN** kiro-cli authentication, model selection, and all governance policy checks remain fully enforced
- **AND** only the inner Linux user-namespace bind-mount step is bypassed

### Requirement: subagent_max_turns ceiling documentation

The transport SHALL set `subagent_max_turns` from `GA_SUBAGENT_MAX_TURNS` (default 200). Documentation SHALL identify 1000 as the KiroCrew 0.6.0 ceiling and state that higher values may be clamped or rejected.

#### Scenario: Default subagent_max_turns is within 0.6.0 ceiling
- **WHEN** `GA_SUBAGENT_MAX_TURNS` is unset
- **THEN** `subagent_max_turns` is patched to 200, which is within the KiroCrew 0.6.0 ceiling of 1000

#### Scenario: GA_SUBAGENT_MAX_TURNS up to 1000 is accepted
- **WHEN** `GA_SUBAGENT_MAX_TURNS=1000`
- **THEN** `subagent_max_turns` is patched to 1000 without a gateway rejection

#### Scenario: GA_SUBAGENT_MAX_TURNS above 1000 behaviour
- **WHEN** `GA_SUBAGENT_MAX_TURNS=2000`
- **THEN** the transport writes 2000 to the config; KiroCrew 0.6.0 may clamp or reject this at runtime. Operators should stay within the documented ceiling.

### Requirement: Bounded in-process memory for task timestamp tracking

On each `_pickup_single` and `_pickup_list`, transport SHALL evict completed `_task_timestamps` entries older than `_TASK_TIMESTAMP_TTL_SECS` (default 3600s), under its lock after updating current timestamps. It SHALL scan only completed entries. `GA_TASK_TIMESTAMP_TTL_SECS` SHOULD configure the TTL.

#### Scenario: Completed task entries are evicted after TTL

- **GIVEN** a transport process that has dispatched many tasks over several hours
- **WHEN** `_pickup_single` or `_pickup_list` is called for a task
- **THEN** any entries in `_task_timestamps` whose `completed_at` is more than `_TASK_TIMESTAMP_TTL_SECS` seconds in the past are removed from the map before the call returns

#### Scenario: Active task entries are not evicted

- **GIVEN** a task that is still running (no `completed_at`)
- **WHEN** eviction runs
- **THEN** that task's timestamp entry is retained

### Requirement: Active crew limit enforced before restart

Before starting a stopped crew, `_ensure_crew_running` SHALL enforce `GA_MAX_ACTIVE_CREWS` (default 3) using actual Podman state. It SHALL exclude and correct stale registry entries marked running but not running in Podman. This memory limit is independent of the total registered-crew limit.

#### Scenario: Active limit not reached
- **WHEN** `_ensure_crew_running` is called for a stopped crew and fewer than
  `GA_MAX_ACTIVE_CREWS` crew containers are currently running according to Podman
- **THEN** the crew container is started normally

#### Scenario: Active limit reached
- **WHEN** `_ensure_crew_running` is called for a stopped crew and
  `GA_MAX_ACTIVE_CREWS` crew containers are actually running in Podman
- **THEN** `_ensure_crew_running` raises a clear error indicating the active crew
  limit and instructing the operator to wait for a running crew to idle out or nuke one

#### Scenario: Stale registry entry excluded from active count
- **WHEN** `_ensure_crew_running` counts running crews and a registry entry has
  `status: "running"` but `container_is_running` returns false for its container
- **THEN** that entry is NOT counted toward `GA_MAX_ACTIVE_CREWS` and its
  registry status is corrected to `"stopped"`

#### Scenario: Already-running crew is unaffected
- **WHEN** `_ensure_crew_running` is called for a crew that is already running
- **THEN** the active limit check is skipped — the crew is not counted a second time

#### Scenario: GA_MAX_ACTIVE_CREWS=0 disables the limit
- **WHEN** `GA_MAX_ACTIVE_CREWS` is set to `0`
- **THEN** the active limit check is skipped entirely — no cap on running crews

### Requirement: Authentication gate precedes registry write in launch
The system SHALL check for a valid auth file at the very start of `launch`, before writing any placeholder into the crew registry. If no valid auth is present, `launch` SHALL initiate the device auth flow and return the `login_url` and `code` in the error response so the caller can complete authentication and then retry `launch` without a separate API call. The crew registry SHALL NOT be modified when launch fails the auth gate.

#### Scenario: launch called before authentication
- **WHEN** `launch` is called and no valid auth file exists
- **THEN** the device auth flow is initiated automatically, the response includes `error: "not_authenticated"`, `login_url`, and `code` (or `null` if the URL could not be extracted within the timeout), no registry entry is written for the crew, and the caller can open the `login_url`, complete auth, and retry `launch` without calling `POST /login` first

#### Scenario: launch called while a login flow is already pending
- **WHEN** `launch` is called, no valid auth file exists, and a login flow is already in progress
- **THEN** the response includes `error: "not_authenticated"` and `login_pending: true` indicating the caller should poll `GET /login` before retrying

#### Scenario: launch called after completing auth
- **WHEN** `launch` is called and a valid auth file exists
- **THEN** the auth gate passes, the registry placeholder is written, and launch proceeds normally

### Requirement: Crew auto-start serialised per crew
`_ensure_crew_running` SHALL guard each crew's probe/start with a per-crew asyncio lock. Same-crew callers wait and recheck before returning, avoiding duplicate starts; different crews remain concurrent.

#### Scenario: Concurrent auto-start calls for the same crew
- **WHEN** two or more callers invoke `_ensure_crew_running` concurrently for the same `crew_id` while the crew container is stopped
- **THEN** `container_start` is called exactly once for that crew, and all callers receive an updated crew dict reflecting the running state

#### Scenario: Concurrent auto-start calls for different crews
- **WHEN** two callers invoke `_ensure_crew_running` concurrently for different `crew_id` values
- **THEN** both start sequences proceed concurrently without being serialised against each other

#### Scenario: Second caller sees already-running container
- **WHEN** a second caller acquires the per-crew lock after the first has already completed the start
- **THEN** the second caller finds the container already running and returns immediately without issuing another `container_start`

### Requirement: crews() active_crews reflects actual Podman state

`crews()` SHALL count only registry-running crews confirmed running by Podman. It SHALL report stale entries as stopped and correct their registry status.

#### Scenario: Registry-running crew whose container is actually running
- **WHEN** `crews()` is called and a crew has `status: "running"` in the registry
  and its Podman container is confirmed running
- **THEN** that crew appears with `status: "running"` and is counted in `active_crews`

#### Scenario: Registry-running crew whose container is externally stopped
- **WHEN** `crews()` is called and a crew has `status: "running"` in the registry
  but its Podman container is not running
- **THEN** that crew appears with `status: "stopped"` in the response, is NOT
  counted in `active_crews`, and the registry entry is corrected to `"stopped"`

#### Scenario: active_crews matches confirmed running container count
- **WHEN** `crews()` is called after one or more crew containers have been
  stopped outside ghostship (e.g. via `podman stop` or a VM reboot)
- **THEN** `active_crews` equals the number of containers that are actually
  running in Podman, not the number of registry entries with `status: "running"`

### Requirement: Idle monitor releases registry lock before container_stop
The idle monitor SHALL release `_registry_lock` before calling `container_stop` on a crew container. An in-flight state flag SHALL be set inside the lock before releasing it to prevent a concurrent idle monitor tick from issuing a second `container_stop` on the same container. The lock SHALL be re-acquired for the subsequent registry write-back after `container_stop` returns.

#### Scenario: Registry lock is not held during container_stop
- **WHEN** the idle monitor stops a crew container
- **THEN** `_registry_lock` is released before the blocking `container_stop` call, so concurrent registry reads and writes (launch, dispatch, schedule monitor) can proceed during the stop

#### Scenario: Double-stop is prevented by in-flight flag
- **WHEN** two idle monitor ticks overlap and both identify the same crew as idle
- **THEN** only one issues `container_stop`; the second detects the in-flight flag and skips

### Requirement: _ensure_crew_running checks registry entry after container_start
After `container_start` returns and before proceeding with post-start setup (cookie write, member enrollment, etc.), `_ensure_crew_running` SHALL verify that the crew's registry entry still exists. If the entry has been removed (e.g. by a concurrent `nuke()`), the function SHALL log an info message and return without error, treating the removal as an intentional teardown.

#### Scenario: Nuke during restart is handled gracefully
- **WHEN** `nuke()` removes a crew's registry entry while `_ensure_crew_running` is mid-restart
- **THEN** `_ensure_crew_running` detects the missing entry after `container_start`, skips post-start setup, and returns without error or spurious log noise

### Requirement: /continue path detection uses endswith, not substring match
`_crew_api_with_recovery` SHALL detect the `/continue` path component using `path.endswith('/continue')` rather than `'continue' in path`, to avoid false matches on future routes containing "continue" as a substring.

#### Scenario: /continue path is correctly identified
- **WHEN** `_crew_api_with_recovery` handles a 400 response on path `/api/spawn/abc123/continue`
- **THEN** the path is correctly identified as a /continue path and cookie-refresh recovery is skipped

#### Scenario: Non-/continue path containing "continue" is not misidentified
- **WHEN** `_crew_api_with_recovery` handles a 400 response on a hypothetical path `/api/continue-session/abc`
- **THEN** the path is NOT identified as a /continue path and normal cookie-refresh recovery proceeds

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

### Requirement: Gateway error detail reaches the caller
When a request to a crew gateway ends in an HTTP error response after the transport's recovery attempts are exhausted, the error returned to the caller SHALL include the final HTTP status code and the gateway's response body, truncated to at most 500 characters. Any session cookie or token value SHALL be redacted from that text. This SHALL NOT change which responses trigger recovery or how many retries are made.

#### Scenario: Unknown persona is reported, not just "unresponsive"
- **WHEN** a dispatch to a crew whose gateway answers `POST /api/spawn` with HTTP 400 and a body naming an unknown agent exhausts recovery
- **THEN** the error returned to the MCP caller includes `400` and the gateway's reason (for example that agent `ghost` was not found), alongside the existing recovery summary

#### Scenario: Long or credential-bearing bodies are bounded
- **WHEN** the gateway's final error body is longer than 500 characters or contains the crew's session cookie value
- **THEN** the caller receives at most 500 characters of it, with the cookie value replaced by a redaction marker

#### Scenario: Recovery behaviour is unchanged
- **WHEN** a crew gateway returns 400, 401 or 403
- **THEN** cookie refresh, container restart and retry limits behave exactly as under "CSRF/cookie auto-recovery on stale credentials"

### Requirement: Cookie refresh is atomic under the registry lock

The transport SHALL update the in-memory crew entry's `cookie` field inside the
registry lock, atomically with the registry persistence call. No window SHALL exist
between the registry save and the in-memory update during which a concurrent reader
could observe a stale cookie value.

#### Scenario: Concurrent request sees fresh cookie after refresh
- **WHEN** `_refresh_cookie` completes for crew X
- **THEN** any concurrent request reading `crew["cookie"]` for crew X sees either
  the old cookie (before lock acquisition) or the new cookie (after release), never
  a state where the registry has the new cookie but the dict still has the old one

### Requirement: Reconcile registry deletion is timestamp-guarded

`_reconcile_registry` SHALL NOT delete a crew entry that was re-registered between
the snapshot and the write-back. Before deleting any entry from `to_remove`, the
transport SHALL verify under the write-back lock that the entry's `created_at`
timestamp matches the value captured in the snapshot.

#### Scenario: Concurrent launch prevents stale reconcile deletion
- **WHEN** `_reconcile_registry` marks crew X for removal
- **AND** a concurrent `launch()` re-registers crew X with a new `created_at` before
  the write-back lock is acquired
- **THEN** the reconcile write-back DOES NOT delete the new crew X entry

#### Scenario: Genuinely stale entry is still removed
- **WHEN** `_reconcile_registry` marks crew X for removal
- **AND** no concurrent launch re-registers crew X
- **THEN** the reconcile write-back removes crew X as normal

### Requirement: ensure_running leader election is single-lock

The early-in-progress check and the leader election in `ensure_running` SHALL be
performed under a single lock acquisition. No lock-free read of startup state SHALL
precede the locked election.

#### Scenario: Only one caller wins leader election under concurrency
- **WHEN** two concurrent callers both enter `ensure_running` for the same crew
- **THEN** exactly one becomes the leader (starts the container)
- **THEN** the other becomes a waiter (blocks until the leader signals readiness)
- **THEN** the container is started exactly once

### Requirement: slot=True falls back with a warning in dispatch

When `_resolve_dispatch_slot()` receives `slot=True`, the transport SHALL log a
warning and treat it as `slot=None` (defaulting to the enrolled member slot
behaviour). It SHALL NOT silently produce headless dispatch without any indication
to the caller.

#### Scenario: slot=True logs a warning and resolves as None
- **WHEN** `dispatch()` is called with `slot=True`
- **THEN** the transport logs a WARNING indicating `slot=True` is not a valid value
- **THEN** the dispatch proceeds as if `slot=None` was passed

### Requirement: Idle stop and crew wake are serialized
The transport SHALL coordinate an idle monitor's container stop with any concurrent operation that wakes or restarts the same crew. A wake SHALL NOT report success while an idle stop can still stop that crew afterward. If an idle stop has already begun, the wake SHALL wait for that stop to finish and then ensure the crew is running before returning.

#### Scenario: Wake starts after idle stop is claimed
- **WHEN** the idle monitor has claimed an idle crew for stopping and a dispatch concurrently requires that crew
- **THEN** the dispatch does not report the crew running before the stop completes
- **THEN** the dispatch ensures the container is running after the stop and the final registry status is `running`

#### Scenario: Crew activity advances before idle stop is claimed
- **WHEN** a crew is touched by a wake or dispatch before the idle monitor claims its stop
- **THEN** the idle monitor observes the activity and skips stopping the crew
- **THEN** the crew remains running
