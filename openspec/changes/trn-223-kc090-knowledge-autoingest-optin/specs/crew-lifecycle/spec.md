## MODIFIED Requirements

### Requirement: Headless crew config overrides
The `_patch_crew_config()` function SHALL write a fixed set of overrides into each crew's
`config.local.json` at launch, covering not just the `agent` section but also `stt`,
`session`, `telemetry`, and top-level keys.

The fixed overrides for all spec-ops crews are:

| Config path | Value | Rationale |
|---|---|---|
| `stt.enabled` | `false` | No microphone in a headless server crew |
| `session.eager_spawn` | `false` | No interactive user; spawn on first dispatch only |
| `session.timeout_secs` | `300` | Reclaim session memory within 5 min of task completion |
| `session.watchdog_rss_max_mb` | `2000` | Hard RSS ceiling per session; recycle if exceeded (above ~1.9 GB active task peak) |
| `telemetry.beacon_enabled` | `false` | No outbound beacon on server deployment |
| `auto_update` | `false` | Prevent version drift on a pinned container image |

Knowledge auto-ingest is **not** written into `full_overrides`. As of KiroCrew 0.9.0
(PR #2448) knowledge auto-ingest is opt-in and already defaults off upstream. Verification
against the pinned base image (`kiro_crew` 0.9.0rc4) established there is no single
`knowledge.auto_ingest` boolean to pin — the toggles are separate fields
(`auto_ingest_artifacts`, `auto_add_documents`), each defaulting to `false` — so pinning one
would write an inert dead key. The disabled posture therefore relies on the verified
upstream default (decision D1 = Option B), guarded by a CI regression test rather than a
config pin. `full_overrides` SHALL NOT contain a `knowledge` section.

The `patch_crew_config.py` container script SHALL accept a full config override
dict (not just agent-scoped keys) and deep-merge all top-level sections into
`config.local.json`. This deep-merge capability is unchanged by this change; it already
supports any future top-level section (including `knowledge`) should an operator opt in,
with no patcher change required.

#### Scenario: Fresh crew launch has headless overrides applied
- **WHEN** a crew container starts for the first time
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
