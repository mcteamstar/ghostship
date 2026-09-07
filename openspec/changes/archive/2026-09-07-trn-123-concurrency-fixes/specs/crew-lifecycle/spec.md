## ADDED Requirements

### Requirement: Crew auto-start serialised per crew
The `_ensure_crew_running` function SHALL serialise the probe-then-start sequence on a per-crew asyncio lock so that at most one caller at a time executes the "is container running?" → `container_start` critical section for a given `crew_id`. Concurrent callers for the same crew SHALL wait on the lock and, once unblocked, verify the container is now running before returning; they SHALL NOT each independently issue a `container_start`. Concurrent callers for **different** crew IDs SHALL NOT be serialised against each other.

#### Scenario: Concurrent auto-start calls for the same crew
- **WHEN** two or more callers invoke `_ensure_crew_running` concurrently for the same `crew_id` while the crew container is stopped
- **THEN** `container_start` is called exactly once for that crew, and all callers receive an updated crew dict reflecting the running state

#### Scenario: Concurrent auto-start calls for different crews
- **WHEN** two callers invoke `_ensure_crew_running` concurrently for different `crew_id` values
- **THEN** both start sequences proceed concurrently without being serialised against each other

#### Scenario: Second caller sees already-running container
- **WHEN** a second caller acquires the per-crew lock after the first has already completed the start
- **THEN** the second caller finds the container already running and returns immediately without issuing another `container_start`
