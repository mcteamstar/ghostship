# crew-lifecycle/configuration Specification

## Purpose

Defines configuration applied to a crew at launch and restart.

## Requirements

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

### Requirement: dangerously_skip_permissions usage is annotated
Any call site in the codebase that passes `dangerously_skip_permissions=True` SHALL include an inline comment explaining why the permission bypass is required and what threat model constraint that implies.

#### Scenario: dangerously_skip_permissions call site has explanatory comment
- **WHEN** a developer reads the code at the `dangerously_skip_permissions=True` call site
- **THEN** the comment explains the purpose of the bypass and the security implication of enabling it

### Requirement: Configurable model default patch
`_patch_crew_config` SHALL set `agent.model` from the selected backend's default model, falling back to `KC_MODEL_DEFAULT` and then KiroCrew's built-in default, and set `agent` from `GA_CREW_AGENT` (default `kiro`). A per-backend override SHALL patch every agent for that backend and take precedence over per-agent model pins. A dispatch-time model SHALL take precedence for that task only. Document these settings and their precedence.

#### Scenario: KC_MODEL_DEFAULT set
- **WHEN** the transport is started with `KC_MODEL_DEFAULT=anthropic/claude-sonnet-4`
- **THEN** every new crew's `config.local.json` contains `agent.model: "anthropic/claude-sonnet-4"`

#### Scenario: KC_MODEL_DEFAULT unset
- **WHEN** the transport is started without `KC_MODEL_DEFAULT`
- **THEN** `_patch_crew_config` writes `agent.model: "auto"`, leaving final model selection to KiroCrew and its backend

#### Scenario: agent field required in config
- **WHEN** `_patch_crew_config` writes `config.local.json`
- **THEN** the `agent` config block includes an `agent` field set to the value
  of `GA_CREW_AGENT` (default `"kiro"`), satisfying KiroCrew 0.4.0's
  required-field check

#### Scenario: GA_CREW_AGENT unset uses default
- **WHEN** `GA_CREW_AGENT` is not set
- **THEN** `_patch_crew_config` writes `"agent": "kiro"` into the config block

#### Scenario: Model defaults do not affect per-agent pins
- **WHEN** `KC_MODEL_DEFAULT` or a backend model default is set and an agent JSON contains a non-empty `"model"` field, with no backend override
- **THEN** that agent continues to use its own pinned model; defaults apply only when no per-agent model is configured

#### Scenario: Backend override beats per-agent model
- **WHEN** `backends.codex.model.override` is set and an agent JSON contains a different `"model"` value
- **THEN** `_patch_models` writes the Codex override into every agent JSON's `"model"` field for Codex crews

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
