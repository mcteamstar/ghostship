# Crew Lifecycle Specification

## Purpose

Manage the creation and teardown of isolated KiroCrew "crew" containers on demand, so agent work happens in dedicated, disposable environments rather than a single shared or permanently running instance.
## Requirements
### Requirement: Crew creation via launch
The system SHALL create an isolated crew container with a dedicated workspace volume and a dedicated home volume when `launch` is called with a valid, unique `crew_id`. The container image and manifest path SHALL be resolved from the crew-type registry based on the optional `composition` parameter (defaulting to `"kirocrew"`).

#### Scenario: First launch for a new crew_id
- **WHEN** `launch` is called with a `crew_id` that has no existing registry entry and the registered crew count is below `GA_MAX_CREWS`
- **THEN** the system creates `gs-vol-<crew_id>` and `gs-home-<crew_id>` volumes, creates and starts a `gs-<crew_id>` container attached to `ga-net` using the image resolved from the crew type registry, and waits up to 30 seconds for its gateway to respond on `:5476`

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
The system SHALL only mark a crew "running" after auth injection, config patching, a config-picking-up restart, agent/skill/steering copy, OpenSpec store seeding, and cookie minting have all succeeded, and SHALL clean up the crew if any required step fails.

#### Scenario: Successful setup
- **WHEN** a crew has confirmed auth and every setup step (auth inject, config patch, restart, agent/skill/steering copy, OpenSpec seed, model patch, cookie mint) succeeds
- **THEN** the crew is registered with status "running", a gateway URL, and a session cookie

#### Scenario: Cookie mint fails
- **WHEN** every earlier setup step succeeds but minting a session cookie fails
- **THEN** the system tears down the container and both volumes and returns an error rather than registering a crew with no usable cookie

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
