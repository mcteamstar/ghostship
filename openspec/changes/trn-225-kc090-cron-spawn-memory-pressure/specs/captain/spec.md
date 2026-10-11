## ADDED Requirements

### Requirement: Captain check-in dispatch is skipped under host memory pressure
When the host is under critical memory pressure, the transport SHALL skip the
`POST /api/spawn` call for a captain check-in and defer to the next scheduled
cron tick rather than making a doomed request that the gateway will refuse.

The skip SHALL NOT advance `current_task_id` or `next_fire_at`. The
`immediate_dispatch_error` field in the check-in result SHALL be set to a
string beginning with the stable marker `memory_pressure:`, with the
available and threshold GB values included for observability.

The check SHALL fail-open: when the memory probe is unavailable (returns no
value or raises), the transport SHALL proceed with the dispatch unconditionally
so that a probe outage does not freeze the crew's check-in schedule.

#### Scenario: Check-in skipped when host memory is below critical threshold
- **WHEN** `_dispatch_captain_checkin` is called and the host available memory is below `GA_RESOURCE_CRITICAL_GB`
- **THEN** the transport SHALL NOT call `POST /api/spawn`
- **THEN** `immediate_dispatch_error` SHALL be set to a string beginning with `memory_pressure:`
- **THEN** `current_task_id` SHALL NOT be updated
- **THEN** `next_fire_at` SHALL NOT be advanced

#### Scenario: Check-in proceeds when host memory is at or above critical threshold
- **WHEN** `_dispatch_captain_checkin` is called and the host available memory is at or above `GA_RESOURCE_CRITICAL_GB`
- **THEN** the transport SHALL call `POST /api/spawn` as normal

#### Scenario: Check-in proceeds when memory probe is unavailable (fail-open)
- **WHEN** `_dispatch_captain_checkin` is called and the memory probe helper returns no value or raises
- **THEN** the transport SHALL proceed with `POST /api/spawn` unconditionally

### Requirement: Captain check-in tracks and escalates sustained memory pressure
The transport SHALL maintain a `consecutive_memory_pressure_skips` counter on
the captain schedule entry. Each memory-pressure skip or gateway memory-pressure
refusal SHALL increment the counter. A successful dispatch SHALL reset it to `0`.

When the counter reaches `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` (default `3`),
the transport SHALL send exactly one escalation mail to `admiral@localhost` with
subject `captain check-in deferred — sustained memory pressure <crew_id>`. The
escalation is edge-triggered: once emitted at the boundary, the transport SHALL
NOT re-emit on subsequent cycles while the counter remains at or above the bound.

#### Scenario: Escalation sent exactly once when sustained pressure threshold is crossed
- **WHEN** `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` is `3` and the third consecutive memory-pressure skip or refusal is recorded for a crew
- **THEN** exactly one mail is sent to `admiral@localhost` with subject `captain check-in deferred — sustained memory pressure <crew_id>`

#### Scenario: No re-escalation while pressure persists above the bound
- **WHEN** more than `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` consecutive memory-pressure skips have occurred for a crew
- **THEN** no additional escalation mail is sent (edge-triggered, not level-triggered)

#### Scenario: Counter reset on successful dispatch
- **WHEN** `_dispatch_captain_checkin` succeeds and `current_task_id` is advanced
- **THEN** `consecutive_memory_pressure_skips` is set to `0` for that crew's captain schedule entry

#### Scenario: Missing counter field treated as zero
- **WHEN** a captain schedule registry entry has no `consecutive_memory_pressure_skips` field
- **THEN** the transport treats it as `0` when incrementing

### Requirement: Raven order templates include a memory-pressure refusal branch
The `spec-driven-development.md` and `independent-review.md` captain order
templates SHALL document that a `POST /api/spawn` call MAY be refused by the
gateway under critical host memory pressure.

Each template SHALL instruct Raven to:
- Treat a memory-pressure refusal identically to any other failed spawn: write
  no dispatch confirmation and leave the pending intent marker so the dispatch
  is retried on a later check-in cycle.
- NOT treat a memory-pressure refusal as a completed dispatch.
- NOT retry the refused spawn within the same check-in cycle.
- Count consecutive memory-pressure refused cycles and, after
  `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` consecutive refusals for the same
  dispatch, mail `admiral@localhost` with subject
  `captain check-in deferred — sustained memory pressure <crew_id>`
  (substituting the actual crew id) before holding.

#### Scenario: Raven holds and retries on a memory-pressure refusal
- **WHEN** Raven issues `POST /api/spawn` and receives a memory-pressure refusal (HTTP 503 or 429 whose body names memory pressure)
- **THEN** Raven writes no dispatch confirmation and leaves the pending intent marker active
- **THEN** Raven does NOT treat the cycle as a completed dispatch

#### Scenario: Raven escalates after sustained memory-pressure refusals
- **WHEN** Raven has observed `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` consecutive memory-pressure refusals for the same dispatch intent
- **THEN** Raven mails `admiral@localhost` with subject `captain check-in deferred — sustained memory pressure <crew_id>` (substituting the actual crew id)
- **THEN** Raven holds and does not attempt another spawn in the same cycle
