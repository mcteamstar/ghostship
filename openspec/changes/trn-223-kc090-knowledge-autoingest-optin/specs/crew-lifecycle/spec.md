## MODIFIED Requirements

### Requirement: Headless crew config overrides
The `_patch_crew_config()` function SHALL write a fixed set of overrides into each crew's
`config.local.json` at launch, covering not just the `agent` section but also `stt`,
`session`, `telemetry`, top-level keys, and — as of KiroCrew 0.9.0 — an explicit
`knowledge.auto_ingest` pin.

The fixed overrides for all spec-ops crews are:

| Config path | Value | Rationale |
|---|---|---|
| `stt.enabled` | `false` | No microphone in a headless server crew |
| `session.eager_spawn` | `false` | No interactive user; spawn on first dispatch only |
| `session.timeout_secs` | `300` | Reclaim session memory within 5 min of task completion |
| `session.watchdog_rss_max_mb` | `2000` | Hard RSS ceiling per session; recycle if exceeded (above ~1.9 GB active task peak) |
| `telemetry.beacon_enabled` | `false` | No outbound beacon on server deployment |
| `auto_update` | `false` | Prevent version drift on a pinned container image |
| `knowledge.auto_ingest` | `false` | Knowledge auto-ingest is opt-in under KiroCrew 0.9.0+ (PR #2448); pin it off explicitly so a future upstream default flip cannot silently enable ingest from the mounted worktree |

The `patch_crew_config.py` container script SHALL accept a full config override
dict (not just agent-scoped keys) and deep-merge all top-level sections into
`config.local.json`. A `knowledge` section passed in `full_overrides` SHALL be
written to `config.local.json` under the top-level `knowledge` key via the existing
`_deep_merge()` logic — no patcher change is required.

#### Scenario: Fresh crew launch has headless overrides applied
- **WHEN** a crew container starts for the first time
- **THEN** `config.local.json` contains `stt.enabled = false`, `session.eager_spawn = false`, `session.timeout_secs = 300`, `session.watchdog_rss_max_mb = 2000`, `telemetry.beacon_enabled = false`, and `auto_update = false`

#### Scenario: Knowledge auto-ingest is disabled after headless overrides applied
- **WHEN** `_patch_crew_config` is called on a new crew container running KiroCrew 0.9.0+
- **THEN** `config.local.json` contains `knowledge.auto_ingest = false`
- **AND** no knowledge auto-ingest path (file-watcher, git commit hook, clipboard capture) is active

#### Scenario: Upstream default flip cannot silently enable ingest
- **GIVEN** `knowledge.auto_ingest = false` is pinned in `full_overrides`
- **WHEN** a future KiroCrew version changes its built-in default for `knowledge.auto_ingest` back to `true`
- **THEN** the crew still runs with auto-ingest disabled, because `config.local.json` is deep-merged over `config.json` and the explicit pin takes precedence

#### Scenario: Upgrade from KiroCrew 0.8.x to 0.9.0 is a no-op for ingest
- **WHEN** an existing crew's base image is bumped from `0.8.x` to `0.9.0+`
- **THEN** the crew's auto-ingest behaviour is identical before and after the upgrade (disabled in both versions)

#### Scenario: Knowledge section deep-merges without patcher change
- **WHEN** `full_overrides` includes `{"knowledge": {"auto_ingest": false}}`
- **THEN** `config.local.json` contains a top-level `knowledge` object with `auto_ingest: false` after patching
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
