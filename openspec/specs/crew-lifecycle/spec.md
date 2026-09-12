# Crew Lifecycle Specification

## Purpose

Manage the creation and teardown of isolated KiroCrew "crew" containers on demand, so agent work happens in dedicated, disposable environments rather than a single shared or permanently running instance.

## Requirements

### Requirement: Crew creation via launch
The system SHALL create an isolated crew container with a dedicated workspace volume and a dedicated home volume when `launch` is called with a valid, unique `crew_id`. The container image and manifest path SHALL be resolved from the crew-type registry based on the optional `composition` parameter (defaulting to `"kirocrew"`). At launch time, the system SHALL read the `org.ghostship.version` OCI label from the crew container and store it in the registry as `crew_image_version`. The `launch` tool SHALL refuse to create a new crew when the number of registered crews (running + stopped) is at or above `GA_MAX_CREWS` (default: 20). The error message SHALL distinguish between the total-registered limit and the active-running limit.

`launch` gains a `dashboard` parameter (default `null`). When `dashboard=true`, `launch` allocates a port from the configured range, registers it with Portal, stores `dashboard_port` in the registry, and returns `dashboard_url` in the response. When `dashboard=false` or when `dashboard=null` (default) and `GA_DASHBOARD_DEFAULT` is unset or false, no port is allocated and `dashboard_url` is `null`.

When `GA_DASHBOARD_DEFAULT=true`, every `launch()` call behaves as if `dashboard=True` was passed unless the caller explicitly passes `dashboard=False`. The caller-supplied value always wins over the site default. The resolution rule is: `effective_dashboard = dashboard if dashboard is not None else GA_DASHBOARD_DEFAULT`.

#### Scenario: First launch for a new crew_id
- **WHEN** `launch` is called with a `crew_id` that has no existing registry entry and the registered crew count is below `GA_MAX_CREWS`
- **THEN** a new crew container and volumes are created and the crew is registered as "running"

#### Scenario: Launch with composition parameter
- **WHEN** `launch` is called with a valid `crew_id` and `composition="worker"`
- **THEN** the system resolves the `"worker"` crew type's image and manifest from the registry and uses them instead of the hardcoded defaults

#### Scenario: Launch with unknown composition
- **WHEN** `launch` is called with a `composition` value not found in the loaded crew-type registry
- **THEN** the system returns an error listing the available crew types and creates no container

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

### Requirement: Crew teardown via nuke
The system SHALL require explicit confirmation before tearing down a crew, and SHALL remove the crew's container and both volumes completely once confirmed. When `GA_DASHBOARD_PORT_ENABLED=true` and the crew has a `dashboard_port` assigned, `nuke` SHALL stop the listener and release the port before removing the registry entry. The system SHALL NOT frame `nuke` as routine cleanup or a normal post-task step; its documentation and tooling aliases SHALL communicate that it is a destructive workspace teardown intended only when the operator wants to permanently discard the workspace.

#### Scenario: Nuke without confirmation
- **WHEN** `nuke` is called for an existing `crew_id` without `confirm=True`
- **THEN** the system returns the container name, both volume names, and the count of currently active (non-done) tasks, and removes nothing

#### Scenario: Nuke with confirmation
- **WHEN** `nuke` is called for an existing `crew_id` with `confirm=True`
- **THEN** the system stops and removes the crew's container, removes its workspace and home volumes, and removes the crew from the registry

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

`POST /crews/{crew_id}/dashboard` SHALL allocate a UI port and start a listener for an already-running crew (same behaviour as `launch(dashboard=True)`). Returns `{"dashboard_url": "..."}` on success, or a no-op returning the existing `dashboard_url` if the crew already has a dashboard active.

`DELETE /crews/{crew_id}/dashboard` SHALL stop the listener and release the port for a running crew. Returns `{"dashboard_url": null}` on success, or a no-op returning `{"dashboard_url": null}` if no dashboard is active.

Both endpoints respect `GA_API_KEY` auth and `GA_DASHBOARD_PORT_ENABLED`.

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
When `nuke(confirm=True)` is called, the system SHALL attempt to cancel all scheduled jobs from the transport registry by issuing a `DELETE /api/crons/<job_id>` request to the gateway for each job before tearing down the container or removing the registry entry. If the gateway is unreachable, individual cancellation failures SHALL be logged at `WARNING` level and SHALL NOT prevent the nuke from proceeding. The crew registry entry (including all schedule entries) SHALL be removed after teardown regardless of individual cancellation outcomes.

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

The system SHALL only mark a crew "running" after all required setup steps have
succeeded, and SHALL clean up the crew if any required step fails. Auth injection
SHALL be verified by exit code, not by pattern-matching the output string.

The Admiral Ed25519 keypair is established **before** crew setup begins, as part
of container creation rather than as a setup step: the transport generates the
keypair, persists the private seed host-side, registers the public key as a
Podman secret, and attaches that secret to the `container_create` spec. The
public key is therefore present in the container from the moment it first
starts, and no setup step injects it. See the `crew-auth` capability for the
keypair requirements.

The setup steps SHALL execute in dependency order:

1. Wait for gateway (pre-restart)
2. Inject kiro-cli auth (`_inject_auth`)
3. Generate the `policy_signing_key` — before restart, so it is in place before
   the security policy is injected
4. Patch crew config (`_patch_crew_config`) — including the required `agent`
   field sourced from `GA_CREW_AGENT` (default: `"kiro"`)
5. Container restart (auth + config take effect)
6. Wait for gateway (post-restart)
7. Copy agents, skills, steering
8. Seed OpenSpec store
9. Inject security policy (depends only on `policy_signing_key`, not on the
   gateway and not on the Admiral keypair)
10. Wait for KiroCrew to seed built-in agent files (gateway-dependent)
11. Patch model overrides — write `agents` directory files **before** calling
    any gateway endpoint, because the agents directory is write-protected at
    runtime in KiroCrew 0.5.0
12. Mint session cookie
13. Read version label, write registry entry

The host-side write of the Admiral private seed SHALL use `os.fsync` before
closing the file descriptor, so the seed is durable before any standing order
can be signed against it. Durability is no longer about in-container
readability: the private seed never enters the container.

The `_patch_crew_config` call in step 4 (pre-restart) SHALL write the `agent`
field into `config.local.json` so the gateway picks it up on first start. The
field SHALL be sourced from the `GA_CREW_AGENT` transport environment variable
(default: `"kiro"`).

The `_copy_agents` call (step 7) — and any other setup step that writes agent
JSON files into `KIRO_AGENTS_DIR` — SHALL occur **after** the post-restart
gateway is ready and SHALL NOT be called after the gateway is already serving
requests, because KiroCrew 0.5.0 makes the agents directory write-protected at
runtime.

#### Scenario: Successful setup

- **WHEN** all setup steps succeed
- **THEN** the crew is marked "running", and the Admiral public key has been
  present in the container since it first started

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

#### Scenario: Agent files written before runtime write-protection
- **WHEN** `_copy_agents` is called during crew setup
- **THEN** the agent JSON files are written to `KIRO_AGENTS_DIR` during the
  post-restart gateway startup window, before KiroCrew 0.5.0 makes that
  directory write-protected at runtime

### Requirement: Headless crew config overrides

The `_patch_crew_config` function SHALL write a full set of headless-optimised
overrides into each crew's `config.local.json` at launch, covering not just the
`agent` section but also `stt`, `session`, `telemetry`, and top-level keys.

The fixed overrides for all spec-ops crews are:

| Config path | Value | Rationale |
|---|---|---|
| `stt.enabled` | `false` | No microphone in a headless server crew |
| `session.eager_spawn` | `false` | No interactive user; spawn on first dispatch only |
| `session.timeout_secs` | `300` | Reclaim session memory within 5 min of task completion |
| `session.watchdog_rss_max_mb` | `2000` | Hard RSS ceiling per session; recycle if exceeded (above ~1.9 GB active task peak) |
| `telemetry.beacon_enabled` | `false` | No outbound beacon on server deployment |
| `auto_update` | `false` | Prevent version drift on a pinned container image |

The `patch_crew_config.py` container script SHALL accept a full config override
dict (not just agent-scoped keys) and deep-merge all top-level sections into
`config.local.json`.

#### Scenario: Fresh crew launch has headless overrides applied

- **GIVEN** a crew is being launched for the first time
- **WHEN** `_patch_crew_config` is called on the new container
- **THEN** `config.local.json` contains `stt.enabled = false`, `session.eager_spawn = false`, `session.timeout_secs = 300`, `session.watchdog_rss_max_mb = 2000`, `telemetry.beacon_enabled = false`, and `auto_update = false`

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
The system SHALL name every crew-scoped Podman resource with a `gs-` prefix derived from the crew_id, kept entirely separate from the `ga-` prefix used for fixed Ghost Academy infrastructure (`ga-transport`, `ga-net`) — so a `crew_id` can never collide with a fixed infra name, regardless of what the caller picks.

#### Scenario: Resource names for a crew
- **WHEN** a crew is created for `crew_id`
- **THEN** its container is named `gs-<crew_id>`, its workspace volume `gs-vol-<crew_id>`, its home volume `gs-home-<crew_id>`, and it joins the shared `ga-net` network

#### Scenario: crew_id matching an infra name
- **WHEN** a crew is created with `crew_id` equal to `transport` or `net`
- **THEN** the resulting container (`gs-transport` or `gs-net`) does not collide with the fixed `ga-transport` container or `ga-net` network, since `ga-` and `gs-` are different string prefixes

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

Before starting a stopped crew container, the transport SHALL query available
host memory via the Podman info API and gate the launch on sufficient free
memory.

The gate is controlled by three environment variables:

| Variable | Type | Default | Description |
|:---------|:-----|:--------|:------------|
| `GA_MIN_FREE_MEM_GB` | float | 2.0 | Minimum free memory (GB) required to proceed with launch |
| `GA_MEMORY_WAIT_SECS` | int | 60 | Maximum seconds to wait for memory to become available |
| `GA_SPAWN_MIN_MEMORY_GB` | float | 1.5 | Value patched into KiroCrew's `spawn_min_memory_gb` config |

The system SHALL poll in 5-second increments until either sufficient memory is
available or the timeout expires. If timeout expires, the system SHALL return a
human-readable error message including the crew ID, current free memory, and
required threshold — without crashing or triggering an OOM.

#### Scenario: Memory available immediately
- **WHEN** a stopped crew container is being restarted AND available memory exceeds `GA_MIN_FREE_MEM_GB`
- **THEN** the container starts immediately with no delay

#### Scenario: Memory becomes available within timeout
- **WHEN** a stopped crew container is being restarted AND available memory is below `GA_MIN_FREE_MEM_GB` AND memory becomes available within `GA_MEMORY_WAIT_SECS`
- **THEN** the container starts after the wait, with no error

#### Scenario: Memory does not free within timeout
- **WHEN** a stopped crew container is being restarted AND available memory remains below `GA_MIN_FREE_MEM_GB` for the full `GA_MEMORY_WAIT_SECS` duration
- **THEN** the system returns an error: `"Insufficient available memory to start crew <id>: <N>GB free, <T>GB required. Retry in a moment."`

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

The transport SHALL apply operator-configured task timeout and turn limit
overrides to each crew's local configuration at launch time. Both values SHALL
be driven by environment variables with sensible defaults that allow long-running
implementation tasks to complete without hitting the KiroCrew default ceiling.

The following operator-level environment variables SHALL be supported:

| Variable | Default | Description |
|---|---|---|
| `GA_SUBAGENT_TIMEOUT_SECS` | 3600 | Maximum wall-clock seconds per task (subagent_timeout_secs) |
| `GA_SUBAGENT_MAX_TURNS` | 200 | Maximum turns per task (subagent_max_turns) |

Both variables SHALL be documented in `docs/configuration.md`.

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

When the transport starts and discovers a stopped crew container in the
registry, it SHALL apply all pending configuration patches (including
`spawn_min_memory_gb`) to that container before marking it as running, in
the same way patches are applied during initial crew creation.

#### Scenario: Stopped crew restored after transport restart
- **WHEN** `_reconcile_registry` restarts a stopped crew container
- **THEN** `_patch_crew_config` is called on that container before the
  crew is marked as running in the registry

#### Scenario: Config patch idempotent on repeated restarts
- **WHEN** the transport is restarted multiple times and the same crew is
  restored each time
- **THEN** each restart applies `_patch_crew_config` without error, and
  the crew's configuration reflects the current transport defaults

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
The `_patch_crew_config` function SHALL write `KC_MODEL_DEFAULT` (when set and non-empty) into the crew's `config.local.json` as the `default_model` field inside the `agent` config block. When `KC_MODEL_DEFAULT` is unset or empty, `_patch_crew_config` SHALL NOT write a `default_model` field, leaving KiroCrew's built-in default unchanged. The variable SHALL be documented in `docs/configuration.md`.

The `_patch_crew_config` function SHALL also write the `agent` field into the
`agent` config block, sourced from `GA_CREW_AGENT` (default: `"kiro"`). KiroCrew
0.4.0 requires this field to be present in `config.local.json`; crew creation
fails at the gateway with a 4xx if it is absent at the time the config is read.

The effective model for any given agent is resolved in this precedence order (highest first):
1. `KC_MODEL_OVERRIDE` — transport patches the per-agent `"model"` field directly in every agent JSON file; beats everything
2. Per-agent `"model"` field in the agent JSON (e.g. `academy/agents/*.json`) — explicit per-agent pin
3. `KC_MODEL_DEFAULT` — patched into `config.local.json` as `default_model`; applies when the per-agent field is absent or cleared
4. KiroCrew built-in default — the hardcoded fallback inside KiroCrew when no other override is in effect

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

### Requirement: Crew config patches sandbox=off for Podman rootless compatibility

The `_patch_crew_config` function SHALL write `"sandbox": "off"` into the `agent` block of `config.local.json`. This disables the KiroCrew inner namespace sandbox, which since 0.5.0 performs a `MS_REMOUNT|MS_BIND|MS_RDONLY` bind-mount to seal credential directories read-only and exits rc=1 (fail-closed) if that mount fails. Under Podman rootless the kernel denies this remount with EPERM because user namespaces inside rootless containers do not have the required mount permission; without this override every agent spawn fails immediately with `AcpRuntimeDead`. The `"sandbox": "off"` value is a pre-existing KiroCrew config option — it short-circuits `detect_backend()` to return `"none"` before the mount is attempted. The Podman container itself remains the OS-level isolation boundary.

#### Scenario: Crew spawns succeed on Podman rootless
- **WHEN** a crew is launched on a Podman rootless host (the standard ghostship deployment)
- **THEN** `config.local.json` contains `"sandbox": "off"` inside the `agent` block
- **AND** agent dispatches complete without `AcpRuntimeDead: process exited (rc=1)`

#### Scenario: sandbox=off does not affect authentication or governance
- **WHEN** `"sandbox": "off"` is patched into the crew config
- **THEN** kiro-cli authentication, model selection, and all governance policy checks remain fully enforced
- **AND** only the inner Linux user-namespace bind-mount step is bypassed

### Requirement: Active crew limit enforced before restart

The transport SHALL enforce a separate limit on simultaneously running crew
containers via `GA_MAX_ACTIVE_CREWS` (default: 3). Before starting a stopped
crew container, `_ensure_crew_running` SHALL count the number of currently
running containers by verifying actual Podman container state, not by reading
registry `status` alone. Any registry entry whose `status` is `"running"` but
whose Podman container is not actually running SHALL be excluded from the running
count and SHALL have its registry `status` corrected to `"stopped"` as a side
effect of the check.

This limit protects host memory independently of the registered-crew count: an
operator can keep many idle crews registered while preventing too many from
running simultaneously.

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
The `_ensure_crew_running` function SHALL serialise the probe-then-start sequence on a per-crew asyncio lock so that at most one caller at a time executes the "is container running?" → `container_start` critical section for a given `crew_id`. Concurrent callers for the same crew SHALL wait on the lock and, once unblocked, verify the container is now running before returning; they SHALL NOT each independently issue a `container_start`. Concurrent callers for **different** crew IDs SHALL NOT be serialised against each other.

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

The `crews()` tool SHALL compute `active_crews` by verifying actual Podman
container state for every registry entry whose `status` is `"running"`. A crew
SHALL be included in `active_crews` only if its container is confirmed running
via `container_is_running`. A crew whose registry says `"running"` but whose
container is not actually running SHALL be reported with `status: "stopped"` in
the response and SHALL NOT be counted in `active_crews`. The registry entry for
any such crew SHALL be corrected to `status: "stopped"` as a side effect of
the `crews()` call.

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
