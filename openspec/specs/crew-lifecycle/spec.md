# Crew Lifecycle Specification

## Purpose

Manage the creation and teardown of isolated KiroCrew "crew" containers on demand, so agent work happens in dedicated, disposable environments rather than a single shared or permanently running instance.

## Requirements

### Requirement: Crew creation via launch
The system SHALL create an isolated crew container with a dedicated workspace volume and a dedicated home volume when `launch` is called with a valid, unique `crew_id`. The container image and manifest path SHALL be resolved from the crew-type registry based on the optional `composition` parameter (defaulting to `"kirocrew"`). At launch time, the system SHALL read the `org.ghostship.version` OCI label from the crew container and store it in the registry as `crew_image_version`.

#### Scenario: First launch for a new crew_id
- **WHEN** `launch` is called with a `crew_id` that has no existing registry entry and the registered crew count is below `GA_MAX_CREWS`
- **THEN** the system creates `gs-vol-<crew_id>` and `gs-home-<crew_id>` volumes, creates and starts a `gs-<crew_id>` container attached to `ga-net` using the image resolved from the crew type registry, reads the `org.ghostship.version` label from the container, stores it in the registry entry as `crew_image_version`, and waits up to 30 seconds for its gateway to respond on `:5476`

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

#### Scenario: Max crews reached
- **WHEN** `launch` is called while the number of registered crews is already at or above `GA_MAX_CREWS`
- **THEN** the system returns an error and creates no container

#### Scenario: Gateway does not become ready
- **WHEN** the newly started crew container's gateway does not respond within 30 seconds
- **THEN** the system tears down the container and both volumes it just created and returns an error, leaving no partial registry entry

#### Scenario: Launch image without version label
- **WHEN** `launch` is called and the resolved container image does not carry the `org.ghostship.version` label
- **THEN** the system stores `"unknown"` as `crew_image_version` in the registry and proceeds normally — the missing label is not a launch failure

### Requirement: Crew teardown via nuke
The system SHALL require explicit confirmation before tearing down a crew, and SHALL remove the crew's container and both volumes completely once confirmed. The system SHALL NOT frame `nuke` as routine cleanup or a normal post-task step; its documentation and tooling aliases SHALL communicate that it is a destructive workspace teardown intended only when the operator wants to permanently discard the workspace.

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

### Requirement: Crew setup completion is all-or-nothing
The system SHALL only mark a crew "running" after auth injection, config patching, a config-picking-up restart, agent/skill/steering copy, OpenSpec store seeding, and cookie minting have all succeeded, and SHALL clean up the crew if any required step fails. Auth injection SHALL be verified by exit code, not by pattern-matching the output string.

#### Scenario: Successful setup
- **WHEN** a crew has confirmed auth and every setup step (auth inject, config patch, restart, agent/skill/steering copy, OpenSpec seed, model patch, cookie mint) succeeds
- **THEN** the crew is registered with status "running", a gateway URL, and a session cookie

#### Scenario: Cookie mint fails
- **WHEN** every earlier setup step succeeds but minting a session cookie fails
- **THEN** the system tears down the container and both volumes and returns an error rather than registering a crew with no usable cookie

#### Scenario: Auth injection failure is detected
- **WHEN** the auth injection command exits with a non-zero exit code
- **THEN** the system treats the injection as failed, does not proceed with the remaining setup steps, and tears down the partially-created crew

#### Scenario: Auth injection output is not used as a success signal
- **WHEN** the auth injection command exits with a non-zero exit code but its output contains the word "injected"
- **THEN** the system treats the injection as failed, not as successful

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
