## Purpose

Defines the observable behavior contracts of the crew object model — the typed representation of a crew and its registry — guaranteeing that encapsulating crew state behind objects preserves the exact on-disk serialization, timing semantics, and launch-concurrency behavior that callers and persisted data already depend on.

## ADDED Requirements

### Requirement: Crew serialization round-trip is lossless

The system SHALL represent each crew with a typed model whose serialization to and from the registry file (`crews.json`) is byte-equivalent to the registry entry format that existed before encapsulation. Reading a stored crew entry and writing it back unchanged MUST produce the same set of keys and values, so no persisted field is dropped, renamed, or reordered in a way that changes the stored shape.

#### Scenario: Round-trip preserves a stored entry

- **WHEN** a crew entry is read from `crews.json` into the typed model and then written back without modification
- **THEN** the resulting entry SHALL contain the same keys and values as the original stored entry

#### Scenario: Unknown stored keys do not fault the load

- **WHEN** a `crews.json` entry contains a key the current model does not recognize (for example a field written by a newer or older version)
- **THEN** the load SHALL succeed and treat the crew as valid rather than raising, preserving forward/backward tolerance of the registry format

#### Scenario: Missing optional keys use defaults

- **WHEN** a `crews.json` entry omits an optional field
- **THEN** the model SHALL supply the documented default for that field (for example `acp_backend` defaults to `kiro`, `status` defaults to `stopped`) without error

### Requirement: Warm marker is never persisted

The system SHALL treat a crew's warm-until marker as in-memory state only. The serialized registry entry MUST NOT include the warm marker, and loading a crew from the registry MUST initialize its warm marker to an unset (not-warm) value regardless of prior in-memory state.

#### Scenario: Serialized entry excludes the warm marker

- **WHEN** a crew with a live warm marker is serialized for `crews.json`
- **THEN** the serialized entry SHALL NOT contain the warm-until field

#### Scenario: Loaded crew starts not-warm

- **WHEN** a crew is loaded from a stored registry entry
- **THEN** its warm marker SHALL be unset so the crew reports not-warm until a fresh prewarm occurs

### Requirement: Idle and warm are computed from stored timing

The system SHALL compute whether a crew is idle from its stored last-used timestamp and the configured idle timeout, and whether it is warm from its in-memory warm marker. A crew with no recorded last-used time SHALL NOT be reported as idle.

#### Scenario: Crew past the idle timeout is idle

- **WHEN** a crew's last-used time is older than the idle timeout
- **THEN** the crew SHALL report as idle

#### Scenario: Recently used crew is not idle

- **WHEN** a crew's last-used time is within the idle timeout
- **THEN** the crew SHALL report as not idle

#### Scenario: Never-used crew is not idle

- **WHEN** a crew has no recorded last-used time
- **THEN** the crew SHALL report as not idle

#### Scenario: Warm marker in the future reports warm

- **WHEN** a crew's warm marker is set to a point still in the future
- **THEN** the crew SHALL report as warm, and otherwise as not warm

### Requirement: Registry read-modify-write stays atomic under a single lock

The system SHALL serialize concurrent read-modify-write access to the registry so that interleaved updates from different callers do not lose writes. A caller that reads the registry, mutates a crew, and commits the change MUST do so under the same mutual-exclusion guarantee that the pre-encapsulation lock-and-save pattern provided, and a failed update MUST NOT persist a partial write.

#### Scenario: Concurrent updates do not lose writes

- **WHEN** two callers each read, modify a different crew, and commit through the registry
- **THEN** both updates SHALL be present in the final stored registry

#### Scenario: Failed update does not persist partial state

- **WHEN** a registry update is abandoned because an error occurs before the commit boundary
- **THEN** the registry file SHALL retain its prior contents rather than a partially-applied update

### Requirement: Crew launch serializes concurrent restart attempts

The system SHALL serialize concurrent attempts to bring the same crew to a ready state so that only one restart cycle runs at a time for a given crew, and other callers observe that cycle's outcome rather than starting a competing restart. When a concurrent teardown removes the crew during a restart, the launch operation SHALL report that removal as a distinct outcome rather than returning a ready crew.

#### Scenario: Concurrent ensure-running for one crew runs one restart

- **WHEN** two callers request ready state for the same crew at the same time
- **THEN** exactly one restart cycle SHALL run and the second caller SHALL observe its outcome

#### Scenario: Teardown during restart yields the removal outcome

- **WHEN** a crew is removed by a concurrent teardown while a restart cycle for it is in progress
- **THEN** the launch operation SHALL report the removal outcome rather than returning a ready crew

### Requirement: Public API and endpoints unchanged by the object model

The system SHALL preserve every externally visible MCP tool signature and REST endpoint path and response shape when crew state is encapsulated behind the object model. The object model is an internal change: no tool argument, endpoint path, or response field is added, removed, or renamed by it.

#### Scenario: Tool and endpoint surface is identical

- **WHEN** any existing MCP tool or REST endpoint is invoked after the object model is in place
- **THEN** its accepted arguments, path, and response shape SHALL be identical to the pre-refactor behavior
