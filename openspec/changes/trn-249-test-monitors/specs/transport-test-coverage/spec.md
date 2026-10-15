## ADDED Requirements

### Requirement: _cron_activity_since helper test coverage

The test suite SHALL exercise every branch of `_cron_activity_since` as a
pure-function unit test with no I/O.

#### Scenario: Running cron job reports activity

- **WHEN** `_cron_activity_since` is called with a payload containing a job where `is_running` is `True`
- **THEN** the function SHALL return `True`

#### Scenario: Recently completed cron job reports activity

- **WHEN** `_cron_activity_since` is called with a payload containing a job whose `running_since` or `last_run_ts` timestamp is greater than `last_used`
- **THEN** the function SHALL return `True`

#### Scenario: Stale cron job does not report activity

- **WHEN** `_cron_activity_since` is called with a payload containing a job whose timestamps are all less than or equal to `last_used` and `is_running` is `False`
- **THEN** the function SHALL return `False`

#### Scenario: Empty payload does not report activity

- **WHEN** `_cron_activity_since` is called with an empty dict or an empty jobs list
- **THEN** the function SHALL return `False`

#### Scenario: Non-dict payload does not report activity

- **WHEN** `_cron_activity_since` is called with a non-dict value (e.g. `None`, a list, a string)
- **THEN** the function SHALL return `False`

### Requirement: _cron_has_enabled_job helper test coverage

The test suite SHALL exercise every branch of `_cron_has_enabled_job` as a
pure-function unit test with no I/O.

#### Scenario: Payload with enabled job returns True

- **WHEN** `_cron_has_enabled_job` is called with a payload containing at least one job where `enabled` is `True`
- **THEN** the function SHALL return `True`

#### Scenario: Payload with only disabled jobs returns False

- **WHEN** `_cron_has_enabled_job` is called with a payload where all jobs have `enabled` set to `False` or absent
- **THEN** the function SHALL return `False`

#### Scenario: Empty jobs list returns False

- **WHEN** `_cron_has_enabled_job` is called with a payload whose `jobs` list is empty
- **THEN** the function SHALL return `False`

#### Scenario: Non-dict payload returns False

- **WHEN** `_cron_has_enabled_job` is called with a non-dict value
- **THEN** the function SHALL return `False`

### Requirement: _note_idle_skip helper test coverage

The test suite SHALL exercise `_note_idle_skip` reason-change deduplication.

#### Scenario: First call for a crew logs the reason

- **WHEN** `_note_idle_skip` is called for a crew with no prior entry in `_idle_skip_reasons`
- **THEN** the reason SHALL be logged at INFO level

#### Scenario: Same reason on second call is not re-logged

- **WHEN** `_note_idle_skip` is called twice for the same crew with the same reason
- **THEN** the log SHALL only be emitted once (on the first call)

#### Scenario: Different reason on second call IS logged

- **WHEN** `_note_idle_skip` is called for a crew and then called again with a different reason
- **THEN** the second log SHALL be emitted

### Requirement: _schedule_monitor test coverage

The test suite SHALL exercise `_schedule_monitor` single-iteration logic using
mock registry state and mock `_ensure_crew_running` / `_crew_api` /
`_crew_api_with_recovery` callables. No daemon thread is started in tests.

#### Scenario: Due job fires against crew gateway

- **WHEN** the schedule monitor finds a job whose `next_fire_at` has passed AND `_ensure_crew_running` succeeds AND the gateway reports the job enabled
- **THEN** `_crew_api_with_recovery` SHALL be called with `POST /api/spawn` and `next_fire_at` SHALL be advanced

#### Scenario: Not-yet-due job is skipped

- **WHEN** the schedule monitor finds a job whose `next_fire_at` is in the future
- **THEN** `_crew_api_with_recovery` SHALL NOT be called for that job

#### Scenario: Disabled job is skipped

- **WHEN** the schedule monitor finds a job where `enabled` is `False`
- **THEN** `_crew_api_with_recovery` SHALL NOT be called for that job

#### Scenario: Captain-type job is skipped

- **WHEN** the schedule monitor finds a job with `type == "captain"`
- **THEN** `_crew_api_with_recovery` SHALL NOT be called for that job

#### Scenario: _ensure_crew_running failure advances next_fire_at without firing

- **WHEN** `_ensure_crew_running` raises an exception for a due job
- **THEN** `next_fire_at` SHALL still be advanced in the registry AND `_crew_api_with_recovery` SHALL NOT be called

#### Scenario: Gateway disables job — registry synced and job not fired

- **WHEN** the gateway GET /api/crons response shows a job with `enabled: false`
- **THEN** the registry schedule entry SHALL have `enabled` set to `False` AND `_crew_api_with_recovery` SHALL NOT fire for that job

#### Scenario: One-shot job is disabled and deleted from gateway after fire

- **WHEN** a due job has `one_shot: True` and fires successfully
- **THEN** the registry schedule entry SHALL have `enabled` set to `False` AND `_crew_api_with_recovery` SHALL be called with `DELETE /api/crons/<job_id>`

### Requirement: _idle_monitor test coverage

The test suite SHALL exercise `_idle_monitor` single-iteration logic using
`FakePodmanClient` for container checks and mock HTTP responses for
`/api/spawn` and `/api/crons`. No daemon thread is started in tests.

#### Scenario: Crew with active task is not stopped

- **WHEN** the idle monitor checks a crew AND `/api/spawn` returns at least one agent with `done: false`
- **THEN** `container_stop` SHALL NOT be called AND `last_used` SHALL be updated via `_touch_crew`

#### Scenario: Crew with enabled cron job is not stopped

- **WHEN** the idle monitor checks a crew AND `/api/crons` reports an enabled job
- **THEN** `container_stop` SHALL NOT be called

#### Scenario: Crew with recent cron activity is not stopped

- **WHEN** the idle monitor checks a crew AND `/api/crons` reports a job whose `last_run_ts` is more recent than `last_used`
- **THEN** `container_stop` SHALL NOT be called

#### Scenario: Genuinely idle crew is stopped

- **WHEN** the idle monitor checks a crew AND `last_used` exceeds `GA_IDLE_TIMEOUT_SECS` AND no active tasks or cron jobs exist
- **THEN** `container_stop` SHALL be called AND the registry entry status SHALL be set to `"stopped"`

#### Scenario: Already-stopped container is skipped

- **WHEN** the idle monitor checks a crew whose container is not running
- **THEN** `container_stop` SHALL NOT be called

#### Scenario: auth_required crew is skipped

- **WHEN** the idle monitor encounters a crew with `status == "auth_required"`
- **THEN** `container_stop` SHALL NOT be called for that crew

#### Scenario: Recently used crew within timeout is not stopped

- **WHEN** the idle monitor checks a crew AND `last_used` is within `GA_IDLE_TIMEOUT_SECS`
- **THEN** `container_stop` SHALL NOT be called

#### Scenario: 401 response triggers cookie refresh before stop decision

- **WHEN** the idle monitor's HTTP call to `/api/spawn` returns 401 and `_mint_cookie` returns a new cookie
- **THEN** the system SHALL retry with the refreshed cookie before deciding whether to stop the crew

#### Scenario: Cookie refresh failure causes fail-open skip

- **WHEN** the idle monitor receives 401 AND `_mint_cookie` returns `None`
- **THEN** `container_stop` SHALL NOT be called (fail-open) and the skip reason SHALL be recorded

#### Scenario: Captain schedule hold prevents stop

- **WHEN** the idle monitor detects an enabled captain-type schedule entry in the registry
- **THEN** `container_stop` SHALL NOT be called AND `_touch_crew` SHALL be called

#### Scenario: TOCTOU guard prevents stop when last_used advanced during checks

- **WHEN** `last_used` is updated (via `_touch_crew`) between the initial idle check and the registry lock acquisition
- **THEN** `container_stop` SHALL NOT be called

#### Scenario: _stopping flag prevents duplicate stop

- **WHEN** a crew's registry entry already has `_stopping: True` when the idle monitor acquires the registry lock
- **THEN** `container_stop` SHALL NOT be called a second time

#### Scenario: _stopping flag is cleared after stop completes

- **WHEN** `container_stop` succeeds
- **THEN** the registry entry SHALL have `_stopping` removed AND `status` set to `"stopped"`

#### Scenario: container_stop failure clears _stopping flag but does not update status

- **WHEN** `container_stop` raises an exception
- **THEN** the `_stopping` flag SHALL be cleared AND the registry `status` SHALL NOT be changed to `"stopped"`

### Requirement: _captain_monitor test coverage

The test suite SHALL exercise `_captain_monitor` single-iteration logic using
mock registry state, mock `_ensure_crew_running`, and mock `_steer_captain_checkin`.
No daemon thread is started in tests.

#### Scenario: Due captain entry triggers steer/dispatch

- **WHEN** the captain monitor finds an enabled captain entry with `next_fire_at` in the past AND `_ensure_crew_running` succeeds
- **THEN** `_steer_captain_checkin` SHALL be called AND `next_fire_at` SHALL be advanced

#### Scenario: Not-yet-due captain entry is skipped

- **WHEN** the captain monitor finds a captain entry with `next_fire_at` in the future
- **THEN** `_steer_captain_checkin` SHALL NOT be called

#### Scenario: Disabled captain entry is skipped

- **WHEN** the captain monitor finds a captain entry with `enabled: False`
- **THEN** `_steer_captain_checkin` SHALL NOT be called

#### Scenario: Sentinel file presence auto-pauses captain schedule

- **WHEN** the captain monitor reads the workspace sentinel file AND it is present
- **THEN** the schedule entry `enabled` SHALL be set to `False` AND `_steer_captain_checkin` SHALL NOT be called

#### Scenario: _ensure_crew_running failure advances next_fire_at

- **WHEN** `_ensure_crew_running` raises for a due captain entry
- **THEN** `next_fire_at` SHALL be advanced AND `_steer_captain_checkin` SHALL NOT be called
