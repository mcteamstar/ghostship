# Crew Lifecycle — Delta Spec (TRN-156)

## Requirement: Bounded in-process memory for task timestamp tracking

The transport process SHALL evict completed-task timestamp entries from the in-process `_task_timestamps` store once an entry's `completed_at` timestamp is more than `_TASK_TIMESTAMP_TTL_SECS` (default 3600 seconds) in the past. Eviction SHALL be performed inside the `_task_timestamps_lock` section on each `_pickup_single` and `_pickup_list` call, after updating the timestamps for the current task. The eviction scan SHALL visit only completed entries (those with a non-null `completed_at`). The TTL SHOULD be configurable via an environment variable `GA_TASK_TIMESTAMP_TTL_SECS`.

The transport process SHALL evict stale warm-marker entries from the in-process `_warm_markers` store. Any entry whose recorded monotonic timestamp is more than `_WARM_MARKER_TTL_SECS` seconds old SHALL be removed during the existing `_warm_markers_lock`-guarded section of `_prewarm_crew`. `_WARM_MARKER_TTL_SECS` SHALL default to `max(GA_PREWARM_TTL_SECS * 2, 3600)` — at least one hour regardless of the prewarm TTL configuration.

#### Scenario: Completed task entries are evicted after TTL

- **GIVEN** a transport process that has dispatched many tasks over several hours
- **WHEN** `_pickup_single` or `_pickup_list` is called for a task
- **THEN** any entries in `_task_timestamps` whose `completed_at` is more than `_TASK_TIMESTAMP_TTL_SECS` seconds in the past are removed from the map before the call returns

#### Scenario: Active task entries are not evicted

- **GIVEN** a task that is still running (no `completed_at`)
- **WHEN** eviction runs
- **THEN** that task's timestamp entry is retained

#### Scenario: Warm markers are evicted after TTL

- **GIVEN** a transport process that has prewarmed crews over several hours
- **WHEN** `_prewarm_crew` is called for any crew
- **THEN** any `_warm_markers` entries older than `_WARM_MARKER_TTL_SECS` are removed from the map
