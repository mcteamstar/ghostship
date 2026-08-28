## MODIFIED Requirements

### Requirement: Numeric configuration bounds enforcement
All numeric configuration fields in the KiroCrew settings that carry defined minimum and maximum bounds SHALL be enforced at the API boundary. A `PATCH /api/config/kirocrew` or `PUT /api/config/kirocrew` request that sets a bounded field to a value outside its allowed range SHALL be rejected with a 4xx response. Out-of-range values SHALL NOT be silently clamped to the floor or ceiling.

Known enforced bounds (verify against 0.4.0 release notes before implementation):
- `subagent_auto_max`: max 64
- `chat_turn_timeout_secs`: min 300
- `session.pool_size`: max 10

The field `spawn_min_memory_gb` with value `0` SHALL continue to be accepted as a valid sentinel that disables the per-spawn memory check. If 0.4.0 introduces a floor bound on this field, ghostship SHALL use `admission_gate: false` as the fallback disable mechanism.

#### Scenario: In-range value accepted
- **WHEN** a config write sets a bounded field to a value within its allowed range
- **THEN** the request succeeds and the value is stored as written

#### Scenario: Out-of-range value rejected
- **WHEN** a config write sets a bounded field to a value outside its allowed range
- **THEN** the request is rejected with a 4xx response and the previous value is preserved

#### Scenario: spawn_min_memory_gb: 0 accepted
- **WHEN** `spawn_min_memory_gb` is set to `0` via the config API
- **THEN** the value is accepted and the per-spawn memory check is disabled

### Requirement: Config path $VAR expansion
Any configuration field that accepts a filesystem path SHALL reject a value containing an unexpanded shell variable reference (a string matching the pattern `$[A-Za-z_][A-Za-z0-9_]*` or `${...}`). The caller SHALL expand all environment variable references before writing via the API.

#### Scenario: Unexpanded $VAR in path field rejected
- **WHEN** a config write sets a path field to a value containing a literal `$VARIABLE` string
- **THEN** the request is rejected with a 4xx response citing the unexpanded variable

#### Scenario: Expanded path accepted
- **WHEN** a config write sets a path field to a fully-resolved absolute path with no `$` characters
- **THEN** the request succeeds

### Requirement: MCP server pooling defaults
An MCP server that declares an `env` block SHALL be pooled by default across crew sessions. A server that maintains per-session state or per-session credentials SHALL declare `"poolable": false` in its configuration to opt out of pooling. A non-poolable server SHALL receive a dedicated instance per session.

#### Scenario: Env-declaring server pooled by default
- **WHEN** an MCP server configuration includes an `env` block and does not set `"poolable": false`
- **THEN** the server is shared (pooled) across crew sessions

#### Scenario: Non-poolable server gets dedicated instance
- **WHEN** an MCP server configuration sets `"poolable": false`
- **THEN** each crew session that uses the server receives its own dedicated instance

#### Scenario: Stateless server unaffected by pooling
- **WHEN** an MCP server declares no `env` block
- **THEN** pooling behaviour is unchanged from 0.3.x defaults
