# crew-lifecycle/capacity Specification

## Purpose

Defines host and crew capacity checks and admission limits.

## Requirements

### Requirement: Pre-launch memory gate

Before waking a stopped crew, transport SHALL require headroom from Linux `MemAvailable` or Podman info elsewhere. It polls every five seconds until `GA_MIN_FREE_MEM_GB` (2.0 default) is met or `GA_MEMORY_WAIT_SECS` (60 default) expires; timeout or unknown memory fails closed with crew, available, and required values. Patch `spawn_min_memory_gb` from `GA_SPAWN_MIN_MEMORY_GB` (1.5 default).

#### Scenario: Linux admission uses MemAvailable
- **WHEN** a stopped crew container is being restarted on Linux and `/proc/meminfo` reports `MemAvailable` above `GA_MIN_FREE_MEM_GB`
- **THEN** the container starts immediately even if `MemFree` is below the threshold

#### Scenario: Memory available immediately
- **WHEN** a stopped crew container is being restarted AND available memory exceeds `GA_MIN_FREE_MEM_GB`
- **THEN** the container starts immediately with no delay

#### Scenario: Memory becomes available within timeout
- **WHEN** a stopped crew container is being restarted AND available memory is below `GA_MIN_FREE_MEM_GB` AND memory becomes available within `GA_MEMORY_WAIT_SECS`
- **THEN** the container starts after the wait, with no error

#### Scenario: Memory does not free within timeout
- **WHEN** a stopped crew container is being restarted AND available memory remains below `GA_MIN_FREE_MEM_GB` for the full `GA_MEMORY_WAIT_SECS` duration
- **THEN** the system returns an error: `"Insufficient available memory to start crew <id>: <N>GB available, <T>GB required. Retry in a moment."`

#### Scenario: Linux available memory cannot be determined
- **WHEN** the transport cannot read or parse `MemAvailable` from `/proc/meminfo`
- **THEN** it does not start the crew and returns a clear error that available memory could not be determined

#### Scenario: Non-Linux memory source
- **WHEN** a stopped crew container is being restarted on a non-Linux host
- **THEN** the transport uses the available-memory value reported by Podman info

#### Scenario: Memory gate disabled
- **WHEN** `GA_MIN_FREE_MEM_GB` is set to `0`
- **THEN** the pre-launch memory check is skipped entirely and the container starts unconditionally

### Requirement: Configurable spawn_min_memory_gb patch

The `_patch_crew_config` function SHALL write `GA_SPAWN_MIN_MEMORY_GB` (default
1.5) into the crew's `spawn_min_memory_gb` config field instead of the
hardcoded value `0`.

The `spawn_min_memory_gb` field SHALL be written as a native config file entry
(not via a runtime workaround) because KiroCrew 0.5.0 fixes the loader that
previously ignored this field in config files.

#### Scenario: Default spawn threshold
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is not set
- **THEN** `spawn_min_memory_gb` is patched to `1.5`

#### Scenario: Custom spawn threshold
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is set to `2.0`
- **THEN** `spawn_min_memory_gb` is patched to `2.0`

#### Scenario: spawn_min_memory_gb zero is a valid disable sentinel
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is set to `0`
- **THEN** `spawn_min_memory_gb` is patched to `0` in the config, disabling
  the spawn memory gate inside the crew

#### Scenario: spawn_min_memory_gb written via config file, not workaround
- **WHEN** a stopped crew container is restarted via `_ensure_crew_running`
- **THEN** the stop/start/patch/stop/start workaround sequence is NOT executed;
  instead a single `_patch_crew_config` + restart sequence is used, because
  KiroCrew 0.5.0 reads `spawn_min_memory_gb` from the config file correctly

### Requirement: Configurable resource pressure thresholds

The `_patch_crew_config` function SHALL read `GA_RESOURCE_PRESSURE_GB` (default
2.0) and `GA_RESOURCE_CRITICAL_GB` (default 1.0) from the environment and patch
them into the crew's config, replacing the current hardcoded `0` values.

#### Scenario: Default pressure thresholds
- **WHEN** neither `GA_RESOURCE_PRESSURE_GB` nor `GA_RESOURCE_CRITICAL_GB` is set
- **THEN** `resource_pressure_gb` is patched to `2.0` and `resource_critical_gb` is patched to `1.0`

#### Scenario: Custom pressure thresholds
- **WHEN** `GA_RESOURCE_PRESSURE_GB=3.0` and `GA_RESOURCE_CRITICAL_GB=1.5`
- **THEN** those values are written into the crew config

### Requirement: Active crew limit enforced before restart

Before starting a stopped crew, `_ensure_crew_running` SHALL enforce `GA_MAX_ACTIVE_CREWS` (default 3) using actual Podman state. It SHALL exclude and correct stale registry entries marked running but not running in Podman. This memory limit is independent of the total registered-crew limit.

#### Scenario: Active limit not reached
- **WHEN** `_ensure_crew_running` is called for a stopped crew and fewer than
  `GA_MAX_ACTIVE_CREWS` crew containers are currently running according to Podman
- **THEN** the crew container is started normally

#### Scenario: Active limit reached
- **WHEN** `_ensure_crew_running` is called for a stopped crew and
  `GA_MAX_ACTIVE_CREWS` crew containers are actually running in Podman
- **THEN** `_ensure_crew_running` raises a clear error indicating the active crew
  limit and instructing the operator to wait for a running crew to idle out or nuke one

#### Scenario: Stale registry entry excluded from active count
- **WHEN** `_ensure_crew_running` counts running crews and a registry entry has
  `status: "running"` but `container_is_running` returns false for its container
- **THEN** that entry is NOT counted toward `GA_MAX_ACTIVE_CREWS` and its
  registry status is corrected to `"stopped"`

#### Scenario: Already-running crew is unaffected
- **WHEN** `_ensure_crew_running` is called for a crew that is already running
- **THEN** the active limit check is skipped — the crew is not counted a second time

#### Scenario: GA_MAX_ACTIVE_CREWS=0 disables the limit
- **WHEN** `GA_MAX_ACTIVE_CREWS` is set to `0`
- **THEN** the active limit check is skipped entirely — no cap on running crews
