## MODIFIED Requirements

### Requirement: Env-declaring MCP servers are not pooled by default

KiroCrew 0.5.0 uses per-connection isolation for MCP servers ("misbehaving
servers get isolated per-connection"). Ghostship's `_copy_agents()` SHALL
continue to automatically set `poolable: false` on any server entry that
contains a `headers` field when writing into a crew's `~/.kiro/mcp.json`.
The `poolable` field SHALL remain honoured by 0.5.0; catalogue entries do not
need to declare it explicitly.

#### Scenario: HTTP server with headers gets poolable: false
- **WHEN** a catalogue entry contains a `headers` field
- **THEN** the entry written into the crew's `mcp.json` includes `"poolable": false`

#### Scenario: HTTP server without headers is written as-is
- **WHEN** a catalogue entry has no `headers` field
- **THEN** the entry is written into `mcp.json` without a `poolable` key added

#### Scenario: poolable field still honoured under 0.5.0 per-connection isolation
- **WHEN** a crew runs on KiroCrew 0.5.0 and `mcp.json` contains `"poolable": false`
- **THEN** the gateway respects the field and does not pool that server across
  connections, consistent with 0.4.0 behaviour
