## MODIFIED Requirements

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
- **THEN** `config.local.json` contains `stt.enabled = false`, `session.eager_spawn = false`, `session.timeout_secs = 300`, `session.watchdog_rss_max_mb = 600`, `telemetry.beacon_enabled = false`, and `auto_update = false`

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
