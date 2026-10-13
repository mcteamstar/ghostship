# Spec Delta

## ADDED Requirements

### Requirement: _captain_monitor test coverage
The test suite SHALL include a `TestCaptainMonitor` test class that exercises `_captain_monitor` for at least one complete iteration cycle using mocked crew state and mocked `_steer_captain_checkin` / `_dispatch_captain_checkin`. The class SHALL cover: fire condition met → steer or dispatch called; fire condition not met → neither called; `_ensure_crew_running` raises → error logged, `next_fire_at` advances; `_steer_captain_checkin` raises → error logged and `next_fire_at` still advances (the monitor always advances `next_fire_at` after a due entry regardless of steer outcome; fallback-to-dispatch on stale sessions is delegated to `_steer_captain_checkin` itself, not the monitor).

#### Scenario: Captain monitor fires when scheduled
- **WHEN** the captain monitor ticks and `next_fire_at` is in the past and the crew is running
- **THEN** `_steer_captain_checkin` or `_dispatch_captain_checkin` is called exactly once

#### Scenario: Captain monitor skips when not yet due
- **WHEN** the captain monitor ticks and `next_fire_at` is in the future
- **THEN** neither `_steer_captain_checkin` nor `_dispatch_captain_checkin` is called

### Requirement: _reseed_crew_schedules captain branch test coverage
The test suite SHALL exercise the three captain schedule type branches in `_reseed_crew_schedules`: no existing task → `_dispatch_captain_checkin` called; has living task → neither dispatch nor steer called; session gone (dead task) → `_dispatch_captain_checkin` called and `current_task_id` cleared.

#### Scenario: Captain schedule reseeds with no prior task
- **WHEN** `_reseed_crew_schedules` runs and the captain schedule has no `current_task_id`
- **THEN** `_dispatch_captain_checkin` is called to start a fresh check-in

### Requirement: _append_captain_mail I/O path test coverage
The test suite SHALL exercise `_append_captain_mail` with a mock `container_exec`, covering: signing secret present → signed mail written with valid `X-Admiral-Sig` header; no signing secret → unsigned mail written. Related mailbox read helpers (`_mail_count`, `_read_all_mail_counts`, `_skim_all_mailboxes`) SHALL be tested with mock tar archive responses.

#### Scenario: Captain mail is signed when signing secret is present
- **WHEN** `_append_captain_mail` is called with a crew that has a `signing_secret`
- **THEN** the written mail message contains a valid `X-Admiral-Sig` header

### Requirement: _captain_do_order/status/stop branch test coverage
The test suite SHALL cover the main execution branches in `_captain_do_order` (template resolution, mail delivery, registry write-back, active-task steer branch), `_captain_do_status` (enabled/disabled state, mailbox counts), and `_captain_do_stop` (schedule disable, registry update).

#### Scenario: do_order delivers mail and updates registry
- **WHEN** `_captain_do_order` is called with a valid standing order
- **THEN** `_append_captain_mail` is called and the registry schedule entry is updated with the new order
