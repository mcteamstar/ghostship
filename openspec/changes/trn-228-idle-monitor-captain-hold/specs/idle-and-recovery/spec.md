# Spec Delta

## MODIFIED Requirements

### Requirement: Idle container stop
The system SHALL stop a crew's container after it has had no active dispatched tasks, no running cron execution, and no cron execution since its last activity for `GA_IDLE_TIMEOUT_SECS`, and SHALL NOT stop a crew that has active work regardless of elapsed idle time. A crew that has just completed setup SHALL have its activity timestamp initialized at setup completion, so the timeout is measured from that point rather than from a missing or zero timestamp. Any enabled gateway cron job — regardless of whether it has fired yet — SHALL by itself count as active work and prevent an idle stop, since an enabled schedule is a standing commitment to run that a fire-history check alone cannot see before its first firing. Any enabled transport-side Captain schedule entry with a real `next_fire_at` (i.e. `next_fire_at < _NEVER_FIRE_AT`) SHALL equally count as active work and prevent an idle stop; Captain schedule entries are not reflected in `/api/crons` and must be checked in the transport registry directly. When the idle monitor cannot determine crew activity due to a transient API error (connection failure, timeout, or unexpected response), it SHALL skip the crew for the current cycle and leave it running — it SHALL NOT proceed to stop a crew whose activity state is unknown.

#### Scenario: Crew with enabled captain schedule is not idle-stopped
- **WHEN** a crew has an enabled captain schedule entry with `next_fire_at` in the near future and no active spawned tasks or gateway crons
- **THEN** the idle monitor does NOT stop the crew

#### Scenario: Crew with disabled captain schedule may be idle-stopped
- **WHEN** a crew has a captain schedule entry with `enabled: false` and no other active work
- **THEN** the idle monitor treats it as idle and may stop the crew after `GA_IDLE_TIMEOUT_SECS`

#### Scenario: Crew with captain schedule at NEVER_FIRE_AT may be idle-stopped
- **WHEN** a crew's captain schedule entry has `next_fire_at == _NEVER_FIRE_AT` (one-shot fired or manually stopped) and no other active work
- **THEN** the idle monitor treats it as idle and may stop the crew after `GA_IDLE_TIMEOUT_SECS`

#### Scenario: Enabled gateway cron still prevents idle stop
- **WHEN** a crew has an enabled gateway cron job (in `/api/crons`) and no active spawned tasks
- **THEN** the idle monitor does NOT stop the crew (existing behaviour preserved)
