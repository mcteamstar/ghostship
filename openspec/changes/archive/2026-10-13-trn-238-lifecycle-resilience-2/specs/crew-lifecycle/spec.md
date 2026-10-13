# Spec Delta

## ADDED Requirements

### Requirement: Idle monitor releases registry lock before container_stop
The idle monitor SHALL release `_registry_lock` before calling `container_stop` on a crew container. An in-flight state flag SHALL be set inside the lock before releasing it to prevent a concurrent idle monitor tick from issuing a second `container_stop` on the same container. The lock SHALL be re-acquired for the subsequent registry write-back after `container_stop` returns.

#### Scenario: Registry lock is not held during container_stop
- **WHEN** the idle monitor stops a crew container
- **THEN** `_registry_lock` is released before the blocking `container_stop` call, so concurrent registry reads and writes (launch, dispatch, schedule monitor) can proceed during the stop

#### Scenario: Double-stop is prevented by in-flight flag
- **WHEN** two idle monitor ticks overlap and both identify the same crew as idle
- **THEN** only one issues `container_stop`; the second detects the in-flight flag and skips

### Requirement: _ensure_crew_running checks registry entry after container_start
After `container_start` returns and before proceeding with post-start setup (cookie write, member enrollment, etc.), `_ensure_crew_running` SHALL verify that the crew's registry entry still exists. If the entry has been removed (e.g. by a concurrent `nuke()`), the function SHALL log an info message and return without error, treating the removal as an intentional teardown.

#### Scenario: Nuke during restart is handled gracefully
- **WHEN** `nuke()` removes a crew's registry entry while `_ensure_crew_running` is mid-restart
- **THEN** `_ensure_crew_running` detects the missing entry after `container_start`, skips post-start setup, and returns without error or spurious log noise

### Requirement: /continue path detection uses endswith, not substring match
`_crew_api_with_recovery` SHALL detect the `/continue` path component using `path.endswith('/continue')` rather than `'continue' in path`, to avoid false matches on future routes containing "continue" as a substring.

#### Scenario: /continue path is correctly identified
- **WHEN** `_crew_api_with_recovery` handles a 400 response on path `/api/spawn/abc123/continue`
- **THEN** the path is correctly identified as a /continue path and cookie-refresh recovery is skipped

#### Scenario: Non-/continue path containing "continue" is not misidentified
- **WHEN** `_crew_api_with_recovery` handles a 400 response on a hypothetical path `/api/continue-session/abc`
- **THEN** the path is NOT identified as a /continue path and normal cookie-refresh recovery proceeds
