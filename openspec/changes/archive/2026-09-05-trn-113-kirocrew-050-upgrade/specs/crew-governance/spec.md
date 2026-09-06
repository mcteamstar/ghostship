## MODIFIED Requirements

### Requirement: Containerfiles pin to kirocrew:0.5.0

All ghostship Containerfiles that reference the KiroCrew base image SHALL pin
to `kirocrew:0.5.0`.

#### Scenario: Containerfile updated to 0.5.0 pin
- **WHEN** a ghostship Containerfile is built after this change
- **THEN** it resolves `FROM ghcr.io/kirodotdev/kirocrew:0.5.0` as the base
  layer and the resulting image is compatible with the 0.5.0 governance API

### Requirement: Numeric config fields are bounds-enforced in KiroCrew 0.5.0

The `_patch_crew_config` function SHALL only write numeric config fields that
fall within KiroCrew 0.5.0's enforced bounds. Any field value outside the
allowed range is rejected with a 4xx response instead of being silently
clamped. The transport SHALL audit each numeric field it writes and ensure its
default and operator-settable range stays within the gateway-enforced bounds.

Fields that carry enforced bounds in 0.5.0 include `spawn_min_memory_gb`,
`resource_pressure_gb`, `resource_critical_gb`, `subagent_timeout_secs`, and
`subagent_max_turns`. A value of `0` for `spawn_min_memory_gb` SHALL remain
a valid disable sentinel and SHALL NOT be rejected by the gateway.

#### Scenario: Numeric field within bounds is accepted
- **WHEN** `_patch_crew_config` writes a numeric field whose value falls within
  KiroCrew 0.5.0's allowed range
- **THEN** the gateway accepts the config and the crew starts normally

#### Scenario: spawn_min_memory_gb=0 is not rejected
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is set to `0` and the gateway enforces bounds
- **THEN** the gateway accepts `spawn_min_memory_gb: 0` as a valid disable
  sentinel and does not return a 4xx

#### Scenario: Out-of-bounds value surfaces a clear error
- **WHEN** `_patch_crew_config` attempts to write a numeric field value outside
  the gateway's enforced range
- **THEN** the gateway rejects the request with a 4xx response, and the
  transport logs the rejection before proceeding with crew teardown

### Requirement: Governance policy templates validated against 0.5.0 stricter validator

KiroCrew 0.5.0 hard-fails crew startup when `security_policy.json` contains a
misspelled `sandbox` key or a malformed `publish` section. Previously these were
silently ignored. The policy templates in `academy/policies/` SHALL be
confirmed well-formed against the 0.5.0 schema before the image pin is bumped.

#### Scenario: Well-formed policy template accepted by 0.5.0 gateway
- **WHEN** a crew starts with a security policy injected from a validated template
- **THEN** the 0.5.0 gateway accepts the policy without a validation error

#### Scenario: Misspelled sandbox key hard-fails in 0.5.0
- **WHEN** `security_policy.json` contains a key spelled `sandox` (or any
  unrecognised key in the `sandbox` section)
- **THEN** the 0.5.0 gateway rejects the policy and the crew fails to start,
  rather than ignoring the misspelling as 0.4.0 did
