# crew-orchestration Specification

## Purpose

Defines runtime resource management and error handling rules for the crew orchestration layer, including the Podman transport client.

## Requirements

### Requirement: PodmanClient resource and error handling

The `PodmanClient` SHALL narrow exception handling in cleanup operations to expected conditions, properly close HTTP resources, and release client connections on shutdown.

#### Scenario: container_stop — unexpected error propagates
- **WHEN** `container_stop` is called and the Podman API returns an unexpected error (not 404/409)
- **THEN** the error is logged at WARNING level and re-raised (not silently swallowed)

#### Scenario: volume_create — 409 conflict is tolerated, other errors propagate
- **WHEN** `volume_create` is called and the volume already exists (HTTP 409)
- **THEN** the call returns without error
- **WHEN** `volume_create` is called and a socket/permission error occurs
- **THEN** the error propagates (not swallowed)

#### Scenario: httpx2 clients are closed on process exit
- **WHEN** the transport process exits normally
- **THEN** the module-level `httpx2.Client` and `httpx2.AsyncClient` in `podman.py` are closed via `atexit`

#### Scenario: container_exec response is closed after use
- **WHEN** `container_exec` completes reading the response body
- **THEN** the response object is closed (no connection pool leak)

#### Scenario: container_exec_pty_stdin raw socket closed on header-phase error
- **WHEN** `container_exec_pty_stdin` raises during the connect or header-read phase
- **THEN** the raw socket is closed before the exception propagates (no fd leak)

### Requirement: Transport probes host memory before a captain check-in spawn

Before a Captain spawn, the transport SHALL compare cached host memory with `GA_RESOURCE_CRITICAL_GB`: below threshold it skips until the next tick, while at/above threshold or unavailable it proceeds. The probe MUST be non-blocking and SHALL NOT wait for memory to free.

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
### Requirement: Transport classifies gateway memory-pressure refusals

A 503 or 429 SHALL count as memory pressure only when its body/reason names memory plus pressure or insufficient; a 503 `still-spawning` response SHALL NOT.

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
