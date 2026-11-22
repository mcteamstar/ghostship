# Spec Delta

## MODIFIED Requirements

### Requirement: CrewLauncher.ensure_running serialises concurrent restart attempts
When multiple callers call `ensure_running` concurrently for the same crew, exactly one SHALL become the leader and perform the restart; the others SHALL wait and receive the refreshed crew dict from the registry. Each waiter SHALL read the outcome for the generation it joined, even if a later generation starts before that read.

#### Scenario: Concurrent callers get a single restart
- **WHEN** two threads call `ensure_running` concurrently for the same stopped crew
- **THEN** `container_start` is called exactly once and both callers receive a crew dict with `status == "running"`

#### Scenario: Leader exception propagates to waiters
- **WHEN** the leader thread's restart fails (e.g. `container_start` raises)
- **THEN** waiters that were blocked on the Event receive the same exception class rather than returning successfully

#### Scenario: Generation counter prevents stale outcome reads
- **GIVEN** a waiter is blocked on generation A and the leader signals generation A's successful outcome
- **WHEN** a third caller starts generation B before the waiter reads its outcome
- **THEN** the waiter receives the successful result for generation A rather than a generation-changed error

#### Scenario: Outcomes remain isolated by generation
- **WHEN** one generation fails and a later generation succeeds before the earlier waiters read their outcomes
- **THEN** each waiter receives only the result recorded for the generation it joined
