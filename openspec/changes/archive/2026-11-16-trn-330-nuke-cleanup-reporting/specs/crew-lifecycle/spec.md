# Spec Delta

## MODIFIED Requirements

### Requirement: Crew teardown via nuke

The system SHALL require explicit confirmation before tearing down a crew. Once confirmed, it SHALL attempt to remove the crew's container and both volumes and SHALL remove the crew from the registry after all cleanup attempts. When `GA_DASHBOARD_PORT_ENABLED=true` and the crew has a `dashboard_port` assigned, `nuke` SHALL stop the listener and release the port before removing the registry entry. The system SHALL NOT frame `nuke` as routine cleanup or a normal post-task step; its documentation and tooling aliases SHALL communicate that it is a destructive workspace teardown intended only when the operator wants to permanently discard the workspace. If any Podman resource cannot be removed, `nuke` SHALL return a cleanup-failure status and identify each resource whose cleanup failed; it SHALL NOT report an unqualified successful teardown.

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
