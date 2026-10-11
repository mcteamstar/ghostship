## ADDED Requirements

### Requirement: Transport probes host memory before a captain check-in spawn
Before calling `POST /api/spawn` for a captain check-in, the transport SHALL
read available host memory via the cached Podman memory helper and compare it
against the `GA_RESOURCE_CRITICAL_GB` threshold. The probe result SHALL
determine whether the spawn call is attempted:

- Below threshold: spawn is skipped, deferred to next cron tick.
- At or above threshold: spawn proceeds normally.
- Probe unavailable (no value or exception): spawn proceeds (fail-open).

The probe MUST be non-blocking. The transport MUST NOT wait or poll for
memory to free before returning control to the cron thread.

#### Scenario: Probe below threshold — spawn skipped
- **WHEN** the host memory probe returns a value below `GA_RESOURCE_CRITICAL_GB`
- **THEN** the transport does not call `POST /api/spawn` for the captain check-in
- **THEN** `immediate_dispatch_error` is set to a string starting with `memory_pressure:`

#### Scenario: Probe at or above threshold — spawn proceeds
- **WHEN** the host memory probe returns a value at or above `GA_RESOURCE_CRITICAL_GB`
- **THEN** the transport calls `POST /api/spawn` as normal

#### Scenario: Probe returns no value — fail-open
- **WHEN** the memory probe helper returns `None`
- **THEN** the transport calls `POST /api/spawn` as normal (no block)

#### Scenario: Probe raises an exception — fail-open
- **WHEN** the memory probe helper raises any exception
- **THEN** the transport calls `POST /api/spawn` as normal (no block)

### Requirement: Transport classifies a gateway memory-pressure spawn refusal
When `POST /api/spawn` is attempted and the gateway refuses with a
memory-pressure signal, the transport SHALL classify that refusal as a
`memory_pressure:` error rather than a generic spawn failure.

Classification criteria: HTTP status 503 or 429 whose response body or reason
phrase names both memory and pressure (or insufficient). A 503
"still-spawning" response (already handled by `_crew_api_with_recovery`) MUST
NOT be reclassified as a memory-pressure refusal.

A classified gateway refusal SHALL NOT be routed through
`_crew_api_with_recovery`'s in-cycle retry phases. The transport SHALL let it
propagate to the same counter and error-recording path as a pre-dispatch skip.

#### Scenario: Gateway memory-pressure 503 classified correctly
- **WHEN** `POST /api/spawn` returns HTTP 503 with a body containing "memory pressure" or "insufficient memory"
- **THEN** `immediate_dispatch_error` is set to a string beginning with `memory_pressure:`
- **THEN** `_crew_api_with_recovery` does NOT retry the request in-cycle

#### Scenario: Gateway memory-pressure 429 classified correctly
- **WHEN** `POST /api/spawn` returns HTTP 429 with a body containing "memory pressure"
- **THEN** `immediate_dispatch_error` is set to a string beginning with `memory_pressure:`

#### Scenario: Gateway 503 still-spawning not misclassified
- **WHEN** `POST /api/spawn` returns HTTP 503 with a still-spawning body (no mention of memory)
- **THEN** the existing `_crew_api_with_recovery` recovery path handles it as before — it is NOT treated as a memory-pressure refusal

#### Scenario: Unrelated HTTP errors not affected
- **WHEN** `POST /api/spawn` returns any HTTP error whose body does not name memory pressure
- **THEN** the error is handled by existing paths and `immediate_dispatch_error` does NOT begin with `memory_pressure:`

### Requirement: New config key GA_SPAWN_PRESSURE_ESCALATE_CYCLES
A new transport configuration key SHALL control how many consecutive
memory-pressure check-in cycles are tolerated before the Admiral is alerted.

| Key | Env var | Type | Default | Meaning |
|---|---|---|---|---|
| `ga_spawn_pressure_escalate_cycles` | `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` | int | `3` | Consecutive memory-pressure check-in cycles before escalation |

The key SHALL be loaded from the environment alongside the existing
`GA_RESOURCE_CRITICAL_GB` and related thresholds.

#### Scenario: Default escalation threshold is 3
- **WHEN** `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` is not set in the environment
- **THEN** the transport treats `ga_spawn_pressure_escalate_cycles` as `3`

#### Scenario: Custom escalation threshold is respected
- **WHEN** `GA_SPAWN_PRESSURE_ESCALATE_CYCLES=5` is set in the environment
- **THEN** the transport escalates to Admiral after 5 consecutive memory-pressure cycles, not 3
