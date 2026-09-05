## ADDED Requirements

### Requirement: Schedule monitor reads gateway cron state as source of truth for enabled status

The schedule monitor SHALL determine whether a job is enabled by reading the `enabled` field from the gateway's `/api/crons` response for the crew, not from the transport registry. The registry's `sched["enabled"]` field SHALL be treated as a reseed bootstrap cache only — the same contract that applies to all other cron state since TRN-82.

When the gateway reports `enabled: false` for a scheduled job, the schedule monitor SHALL skip firing that job and SHALL write `enabled: false` back to the registry entry for that job, keeping the registry in sync with gateway state.

When the crew container is stopped and cannot be woken (gateway is unreachable), the schedule monitor SHALL fall back to the registry's `enabled` field as a best-effort signal — preserving the existing fail-open behaviour for stopped crews.

#### Scenario: Gateway reports job disabled — monitor skips and writes back

- **WHEN** the schedule monitor evaluates a due job and the gateway's `/api/crons` response for that crew lists the job with `"enabled": false`
- **THEN** the monitor does not fire the job, and writes `enabled: false` to the registry entry for that job

#### Scenario: Gateway reports job enabled — monitor fires normally

- **WHEN** the schedule monitor evaluates a due job and the gateway's `/api/crons` response for that crew lists the job with `"enabled": true`
- **THEN** the monitor fires the job as normal (existing behaviour)

#### Scenario: Crew stopped, gateway unreachable — monitor falls back to registry

- **WHEN** the schedule monitor evaluates a job for a crew that cannot be woken (`_ensure_crew_running` raises or the crew was already stopped before the gateway fetch), so the gateway's `/api/crons` response is unavailable
- **THEN** the monitor falls back to the registry's `enabled` field to decide whether to skip; if the registry shows `enabled: false` the job is skipped; if the registry shows `enabled: true` (or the field is absent) the job proceeds with the existing wake-and-fire path

#### Scenario: Gateway cron payload field is absent — monitor treats job as enabled

- **WHEN** the gateway's `/api/crons` response includes a job entry but the `"enabled"` field is absent
- **THEN** the monitor treats the job as enabled and fires it (fail-open, preserving existing behaviour)
