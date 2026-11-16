# Spec Delta

## MODIFIED Requirements

### Requirement: Pre-launch memory gate

Before starting a stopped crew container, the transport SHALL check available
memory and gate the launch on sufficient headroom. On Linux, the transport SHALL
use the kernel's `MemAvailable` value from `/proc/meminfo`; on non-Linux hosts,
it SHALL use the Podman info API's available-memory value.

The gate is controlled by three environment variables:

| Variable | Type | Default | Description |
|:---------|:-----|:--------|:------------|
| `GA_MIN_FREE_MEM_GB` | float | 2.0 | Minimum available memory (GB) required to proceed with launch |
| `GA_MEMORY_WAIT_SECS` | int | 60 | Maximum seconds to wait for memory to become available |
| `GA_SPAWN_MIN_MEMORY_GB` | float | 1.5 | Value patched into KiroCrew's `spawn_min_memory_gb` config |

The system SHALL poll in 5-second increments until either sufficient memory is
available or the timeout expires. If timeout expires, the system SHALL return a
human-readable error message including the crew ID, current available memory,
and required threshold — without crashing or triggering an OOM. If the Linux
`MemAvailable` value cannot be read or parsed, the system SHALL fail closed and
report that available memory could not be determined; it SHALL NOT substitute
raw `MemFree` for admission.

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
