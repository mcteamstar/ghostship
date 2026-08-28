## MODIFIED Requirements

### Requirement: Numeric config fields are bounds-enforced in KiroCrew 0.4.0

The `_patch_crew_config` function SHALL only write numeric config fields that
fall within KiroCrew 0.4.0's enforced bounds. Any field value outside the
allowed range is now rejected with a 4xx response instead of being silently
clamped. The transport SHALL audit each numeric field it writes and ensure its
default and operator-settable range stays within the gateway-enforced bounds.

Fields that carry enforced bounds in 0.4.0 include `spawn_min_memory_gb`,
`resource_pressure_gb`, `resource_critical_gb`, `subagent_timeout_secs`, and
`subagent_max_turns`. A value of `0` for `spawn_min_memory_gb` SHALL remain
a valid disable sentinel and SHALL NOT be rejected by the gateway.

#### Scenario: Numeric field within bounds is accepted
- **WHEN** `_patch_crew_config` writes a numeric field whose value falls within
  KiroCrew 0.4.0's allowed range
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

### Requirement: Config fields with unexpanded shell variable references are rejected

KiroCrew 0.4.0 rejects any config field value that contains a literal `$`
followed by alphanumeric characters or `{…}` (an unexpanded shell variable
reference). The transport SHALL ensure all config field values written to
`config.local.json` are fully expanded before writing — no field value SHALL
contain a literal `$VAR` or `${VAR}` string.

#### Scenario: Fully expanded config value is accepted
- **WHEN** `_patch_crew_config` writes a config field whose value is a fully
  resolved Python string (no literal `$` variable references)
- **THEN** the gateway accepts the field without error

#### Scenario: Unexpanded variable reference is rejected
- **WHEN** a config field value contains a literal string such as `"$HOME"`
  or `"${KIROCREW_DIR}/config"`
- **THEN** the gateway rejects the config with a 4xx response indicating an
  unexpanded variable reference

### Requirement: Env-declaring MCP servers are not pooled by default

KiroCrew 0.4.0 changes the default pooling behaviour: any MCP server spec that
declares an `env` block is now pooled across agents by default, which breaks
stateful servers. Any MCP server spec inside ghostship that declares an `env`
block and whose state is per-agent or per-session SHALL include `"poolable": false`
to opt out of the new default.

#### Scenario: Stateful env-declaring server carries poolable=false
- **WHEN** an MCP server spec in the ghostship crew configuration declares an
  `env` block and manages per-session state
- **THEN** the spec includes `"poolable": false` so KiroCrew 0.4.0 does not
  pool it across agents

#### Scenario: Stateless env-declaring server may omit poolable
- **WHEN** an MCP server spec declares an `env` block and its state is fully
  shared or idempotent across sessions
- **THEN** the absence of `"poolable": false` is intentional and the server
  may be pooled

#### Scenario: MCP server without env block is unaffected
- **WHEN** an MCP server spec declares no `env` block
- **THEN** KiroCrew 0.4.0's new pooling default does not apply to it and no
  change is required

### Requirement: Containerfiles pin to kirocrew:0.4.0

All ghostship Containerfiles that reference the KiroCrew base image SHALL pin
to `kirocrew:0.4.0`. A Containerfile left pinned at `0.3.x` or `latest` will
pull an incompatible base image that does not carry the 0.4.0 API fixes.

#### Scenario: Containerfile updated to 0.4.0 pin
- **WHEN** a ghostship Containerfile is built after this change
- **THEN** it resolves `FROM ghcr.io/kirodotdev/kirocrew:0.4.0` as the base
  layer and the resulting image is compatible with the 0.4.0 API surface

#### Scenario: Old pin triggers build failure
- **WHEN** a Containerfile still references `kirocrew:0.3.x` or `kirocrew:latest`
  after this change is applied
- **THEN** the build CI job fails or the resulting image is flagged as
  incompatible during the regression test pass
