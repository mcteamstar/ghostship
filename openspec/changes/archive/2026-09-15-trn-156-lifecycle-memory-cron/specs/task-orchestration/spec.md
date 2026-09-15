# Task Orchestration — Delta Spec (TRN-156)

## Requirement: Idempotent one-shot job deletion

When the schedule monitor fires a one-shot (delay) job, the system SHALL make the job permanently non-repeating before issuing the gateway DELETE. Specifically, the transport SHALL:

1. Mark the registry entry for the one-shot job as `enabled: false` and set its `next_fire_at` to `_NEVER_FIRE_AT` **atomically under `_registry_lock`** before attempting the gateway DELETE.
2. Then issue `DELETE /api/crons/{job_id}` to the gateway.

If the DELETE succeeds, the registry entry MAY be removed. If the DELETE fails (any exception or non-success response), the job SHALL NOT be re-fired by the schedule monitor in any subsequent cycle, because the registry marks it disabled with `next_fire_at = _NEVER_FIRE_AT`. The DELETE failure SHALL be logged at WARNING level.

This requirement applies whether or not the task dispatch that preceded the DELETE succeeded. The registry update and the gateway DELETE are separate steps: the registry update is the durable safety gate; the DELETE is a best-effort cleanup.

#### Scenario: One-shot job fires successfully, DELETE succeeds

- **WHEN** the schedule monitor fires a one-shot job and the task dispatch succeeds, and the subsequent gateway DELETE of the cron succeeds
- **THEN** the registry entry is marked disabled with `next_fire_at = _NEVER_FIRE_AT` before the DELETE is issued, and the job is not re-fired in any future cycle

#### Scenario: One-shot job fires, DELETE fails

- **WHEN** the schedule monitor fires a one-shot job and the gateway DELETE fails (network error, 404, or gateway timeout)
- **THEN** the registry entry has already been marked disabled with `next_fire_at = _NEVER_FIRE_AT`, the DELETE failure is logged at WARNING level, and the job is not re-fired in any subsequent schedule monitor cycle

#### Scenario: One-shot job replay in subsequent year is prevented

- **GIVEN** a one-shot job whose cron expression contains a wildcard year component (e.g. `30 14 12 9 *`)
- **WHEN** the schedule monitor fires it and the DELETE fails
- **THEN** the registry marks `enabled: false` and `next_fire_at = _NEVER_FIRE_AT` so the wildcard-year expression cannot cause a replay in the next calendar year
