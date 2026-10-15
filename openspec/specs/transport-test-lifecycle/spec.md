# transport-test-lifecycle Specification

## Purpose
Defines the unit test coverage requirements for `transport/lifecycle.py`, covering crew lifecycle management operations (create, start, stop, destroy) and their state transitions. Tests run without a real Podman socket using `FakePodmanClient`.

## Requirements

### Requirement: _cleanup_crew removes container, volumes, and secrets

The test suite SHALL verify that `_cleanup_crew` performs best-effort removal of the crew container, workspace volume, home volume, and admiral public-key Podman secret, tolerating failures on any individual step.

#### Scenario: Full cleanup removes all resources
- **WHEN** `_cleanup_crew` is called with a container and two volumes that exist in `FakePodmanClient`
- **THEN** `container_stop`, `container_remove`, `volume_remove` (twice), and `secret_remove` are all called in order and the resources are absent afterward

#### Scenario: Missing container does not abort volume removal
- **WHEN** `_cleanup_crew` is called and `container_stop` raises a RuntimeError (container already gone)
- **THEN** `volume_remove` is still called for both volumes and `secret_remove` is still called

#### Scenario: Missing volume does not abort secret removal
- **WHEN** `_cleanup_crew` is called and `volume_remove` raises for the workspace volume
- **THEN** `volume_remove` is still called for the home volume and `secret_remove` is still called

#### Scenario: Secret removal is skipped for non-crew container names
- **WHEN** `_cleanup_crew` is called with a container name that does not start with the crew prefix
- **THEN** `secret_remove` is NOT called for an admiral key

### Requirement: CrewLauncher.ensure_running starts a stopped container

`CrewLauncher.ensure_running` SHALL start a stopped crew container, refresh its cookie, update the registry status to `running`, and return an updated crew dict.

#### Scenario: Stopped crew is started and cookie refreshed
- **WHEN** `ensure_running` is called for a crew whose container is not running
- **THEN** `container_start` is called, the registry entry status becomes `"running"`, and the returned crew dict contains the new cookie

#### Scenario: Running crew with live gateway is returned immediately
- **WHEN** `ensure_running` is called for a crew whose container is running and the gateway probe succeeds
- **THEN** `container_start` is NOT called and the original crew dict is returned

### Requirement: CrewLauncher.ensure_running serialises concurrent restart attempts

When multiple callers call `ensure_running` concurrently for the same crew, exactly one SHALL become the leader and perform the restart; the others SHALL wait and receive the refreshed crew dict from the registry.

#### Scenario: Concurrent callers get a single restart
- **WHEN** two threads call `ensure_running` concurrently for the same stopped crew
- **THEN** `container_start` is called exactly once and both callers receive a crew dict with `status == "running"`

#### Scenario: Leader exception propagates to waiters
- **WHEN** the leader thread's restart fails (e.g. `container_start` raises)
- **THEN** waiters that were blocked on the Event receive the same exception class rather than returning successfully

#### Scenario: Generation counter prevents stale outcome reads
- **WHEN** a waiter wakes and the generation counter has incremented (a third caller started a new restart cycle)
- **THEN** the waiter raises a RuntimeError indicating the generation changed rather than reading the stale outcome

### Requirement: ensure_running returns _NUKED_DURING_RESTART sentinel when crew is concurrently nuked

If a concurrent `nuke()` removes the crew's registry entry between `container_start` and post-start setup, `ensure_running` SHALL return the `_NUKED_DURING_RESTART` sentinel rather than raising or returning a stale crew dict.

#### Scenario: Crew nuked after container_start returns sentinel
- **WHEN** `ensure_running` calls `container_start` and then the registry entry is absent
- **THEN** `ensure_running` returns the `_NUKED_DURING_RESTART` object (identity check `is _NUKED_DURING_RESTART`)

#### Scenario: Waiter sees nuked crew after waking
- **WHEN** a waiter wakes and `_get_crew` raises `KeyError` (crew removed during restart)
- **THEN** the waiter returns `_NUKED_DURING_RESTART`

### Requirement: CrewLauncher._check_active_limit blocks restart when limit reached

When `GA_MAX_ACTIVE_CREWS` is set and the number of currently running containers meets or exceeds the limit, `_check_active_limit` SHALL raise `RuntimeError` before `container_start` is called.

#### Scenario: Active limit exceeded raises RuntimeError
- **WHEN** `GA_MAX_ACTIVE_CREWS` is 1 and one container is already running
- **THEN** `_check_active_limit` raises `RuntimeError` with a message mentioning the limit

#### Scenario: Active limit disabled (zero) allows unlimited crews
- **WHEN** `GA_MAX_ACTIVE_CREWS` is 0
- **THEN** `_check_active_limit` does NOT raise regardless of running container count

#### Scenario: Stale running entry corrected to stopped
- **WHEN** `GA_MAX_ACTIVE_CREWS` is 2 and a registry entry has `status == "running"` but the container is not actually running
- **THEN** the entry is corrected to `status == "stopped"` and does NOT count toward the active limit

### Requirement: CrewLauncher._check_memory_gate blocks restart when memory is insufficient

When `GA_MIN_FREE_MEM_GB` is set and available memory is below the threshold, `_check_memory_gate` SHALL raise `RuntimeError` before `container_start` is called.

#### Scenario: Insufficient memory raises RuntimeError
- **WHEN** `GA_MIN_FREE_MEM_GB` is 4.0 and `system_info` reports less than 4 GB available
- **THEN** `_check_memory_gate` raises `RuntimeError` mentioning the memory requirement

#### Scenario: Memory gate disabled (zero) always passes
- **WHEN** `GA_MIN_FREE_MEM_GB` is 0
- **THEN** `_check_memory_gate` does NOT raise regardless of reported memory

### Requirement: State transition graph is fully exercised

The test suite SHALL exercise each valid state transition for a crew: `launching` → `running`, `running` → `stopped`, `stopped` → `running`, and `running` → removed (nuke path).

#### Scenario: launching to running transition
- **WHEN** a crew registry entry has `status == "launching"` and `_finish_crew_setup` succeeds
- **THEN** the registry entry transitions to `status == "running"` with a non-empty `cookie`

#### Scenario: running to stopped transition via _cleanup_crew
- **WHEN** `_cleanup_crew` is called for a running crew container
- **THEN** `container_stop` and `container_remove` are called and the container is absent from `FakePodmanClient`

#### Scenario: stopped to running transition via ensure_running
- **WHEN** a crew has `status == "stopped"` and `ensure_running` is called
- **THEN** the registry transitions to `status == "running"` and the container is running

#### Scenario: running to removed transition via nuke path
- **WHEN** `_cleanup_crew` is called with confirm-style inputs
- **THEN** container, workspace volume, and home volume are all removed from `FakePodmanClient`

### Requirement: _secret_identifier returns a non-reversible opaque label

`_secret_identifier` SHALL return a string of the form `"sha256:" + <16-hex-char digest>` for any input, without exposing the original value.

#### Scenario: Returns sha256 prefix with 16-char hex suffix
- **WHEN** `_secret_identifier` is called with any non-empty string
- **THEN** the result starts with `"sha256:"` and the suffix is exactly 16 lowercase hexadecimal characters

#### Scenario: Different inputs produce different labels
- **WHEN** `_secret_identifier` is called with two distinct strings
- **THEN** the two results are not equal

#### Scenario: Same input always produces the same label
- **WHEN** `_secret_identifier` is called twice with the same string
- **THEN** both calls return the same value
