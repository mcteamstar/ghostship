## MODIFIED Requirements

### Requirement: Env-declaring MCP servers are not pooled by default
KiroCrew 0.4.0 SHALL not pool MCP servers that declare environment variables or auth headers. Ghostship's `_copy_agents()` SHALL automatically set `poolable: false` on any server entry that contains a `headers` field when writing that entry into a crew's `~/.kiro/mcp.json`. Catalogue entries do not need to declare `poolable: false` explicitly.

#### Scenario: HTTP server with headers gets poolable: false
- **WHEN** a catalogue entry contains a `headers` field
- **THEN** the entry written into the crew's `mcp.json` includes `"poolable": false`

#### Scenario: HTTP server without headers is written as-is
- **WHEN** a catalogue entry has no `headers` field
- **THEN** the entry is written into `mcp.json` without a `poolable` key added
