## MODIFIED Requirements

### Requirement: Pre-launch memory gate

Before starting a stopped crew container, the transport SHALL query available
host memory via the Podman info API and gate the launch on sufficient free
memory.

The gate is controlled by three environment variables:

| Variable | Type | Default | Description |
|:---------|:-----|:--------|:------------|
| `GA_MIN_FREE_MEM_GB` | float | 2.0 | Minimum free memory (GB) required to proceed with launch |
| `GA_MEMORY_WAIT_SECS` | int | 60 | Maximum seconds to wait for memory to become available |
| `GA_SPAWN_MIN_MEMORY_GB` | float | 1.5 | Value patched into KiroCrew's `spawn_min_memory_gb` config |

The system SHALL poll in 5-second increments until either sufficient memory is
available or the timeout expires. If timeout expires, the system SHALL return a
human-readable error message including the crew ID, current free memory, and
required threshold — without crashing or triggering an OOM.

#### Scenario: Memory available immediately
- **WHEN** a stopped crew container is being restarted AND available memory exceeds `GA_MIN_FREE_MEM_GB`
- **THEN** the container starts immediately with no delay

#### Scenario: Memory becomes available within timeout
- **WHEN** a stopped crew container is being restarted AND available memory is below `GA_MIN_FREE_MEM_GB` AND memory becomes available within `GA_MEMORY_WAIT_SECS`
- **THEN** the container starts after the wait, with no error

#### Scenario: Memory does not free within timeout
- **WHEN** a stopped crew container is being restarted AND available memory remains below `GA_MIN_FREE_MEM_GB` for the full `GA_MEMORY_WAIT_SECS` duration
- **THEN** the system returns an error: `"Insufficient available memory to start crew <id>: <N>GB free, <T>GB required. Retry in a moment."`

#### Scenario: Memory gate disabled
- **WHEN** `GA_MIN_FREE_MEM_GB` is set to `0`
- **THEN** the pre-launch memory check is skipped entirely and the container starts unconditionally

### Requirement: Configurable spawn_min_memory_gb patch

The `_patch_crew_config` function SHALL write `GA_SPAWN_MIN_MEMORY_GB` (default
1.5) into the crew's `spawn_min_memory_gb` config field instead of the
hardcoded value `0`.

#### Scenario: Default spawn threshold
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is not set
- **THEN** `spawn_min_memory_gb` is patched to `1.5`

#### Scenario: Custom spawn threshold
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is set to `2.0`
- **THEN** `spawn_min_memory_gb` is patched to `2.0`

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
