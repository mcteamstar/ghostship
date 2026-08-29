# mcp-server-config Specification

## Purpose

Defines how MCP servers are declared, catalogued, and injected into crew containers at setup time, giving agents access to external tools without baking server configs into committed files.

## Requirements

### Requirement: MCP server catalogue at academy/mcp/
The ghostship repo SHALL include an `academy/mcp/` directory. Each file in that directory is a named MCP server definition in JSON format, where the filename without extension is the server name. The JSON object SHALL conform to the kiro-cli `mcpServers` entry format (at minimum a `type` field and either a `url` or `command` field). The catalogue MAY be empty; an empty catalogue is valid and produces no MCP servers in deployed crews.

#### Scenario: Catalogue entry defines an HTTP server
- **WHEN** `academy/mcp/armory.json` contains `{"type": "streamable-http", "url": "http://armory.example.com/mcp"}`
- **THEN** a crew deployed from a composition that declares `armory` in its `mcpServers` list receives a `mcp.json` entry named `armory` with that config

#### Scenario: Empty catalogue produces no MCP servers
- **WHEN** `academy/mcp/` exists but contains no JSON files
- **THEN** no `mcp.json` is written into the crew container and no MCP servers are available beyond the agent's own declarations

### Requirement: Composition manifest declares crew-level MCP servers
The composition `manifest.json` MAY include a `mcpServers` array of server names. Each name SHALL be resolved against the `academy/mcp/` catalogue. At crew setup, `_copy_agents()` SHALL write a `~/.kiro/mcp.json` inside the crew container containing the resolved configs for all declared server names.

#### Scenario: Manifest declares servers and crew mcp.json is written
- **WHEN** `crews/spec-ops/manifest.json` contains `{"mcpServers": ["armory", "nexus"]}`
- **THEN** after `_copy_agents()` runs, the crew container has `~/.kiro/mcp.json` with entries for `armory` and `nexus`

#### Scenario: Manifest declares no mcpServers key
- **WHEN** `manifest.json` has no `mcpServers` key
- **THEN** no `~/.kiro/mcp.json` is written into the crew container by the composition step

#### Scenario: Unknown server name is skipped with a warning
- **WHEN** `manifest.json` declares a server name that has no matching file in `academy/mcp/`
- **THEN** `_copy_agents()` logs a warning naming the missing entry and skips it; crew setup continues and the remaining servers are written normally

### Requirement: Secret substitution in catalogue entries
Any `${VAR}` reference in a catalogue entry's field values SHALL be substituted with the corresponding environment variable from the transport container's environment at the time `_copy_agents()` runs. A variable that is absent from the environment SHALL produce a warning log; the literal `${VAR}` string SHALL be written as the value rather than failing crew setup.

#### Scenario: Auth header with environment variable is substituted
- **WHEN** `academy/mcp/nexus.json` contains `{"headers": {"Authorization": "Bearer ${NEXUS_API_KEY}"}}` and `NEXUS_API_KEY` is set in the transport environment
- **THEN** the `mcp.json` written into the crew container contains the resolved token value, not the literal `${NEXUS_API_KEY}` string

#### Scenario: Missing environment variable produces a warning but does not fail setup
- **WHEN** a catalogue entry references `${MISSING_VAR}` and that variable is not set in the transport environment
- **THEN** `_copy_agents()` logs a warning, writes the literal `${MISSING_VAR}` string into the crew's `mcp.json`, and crew setup continues

### Requirement: Agent-level mcpServers in agent JSON
Individual agent JSON files in `academy/agents/` MAY include a `mcpServers` map. These servers are written directly into the agent's own JSON in the crew container and are available to that agent regardless of the composition's `mcp.json`. An agent MAY set `includeMcpJson: false` to opt out of the composition-level `mcp.json` entirely.

#### Scenario: Agent declares its own mcpServers
- **WHEN** `academy/agents/ghost.json` contains a `mcpServers` map
- **THEN** those servers are present in the agent's JSON as written into the crew container by `_copy_agents()`

#### Scenario: Agent opts out of global mcp.json
- **WHEN** an agent JSON sets `includeMcpJson: false`
- **THEN** the agent's JSON is written with that field preserved, and kiro-cli does not consult `~/.kiro/mcp.json` when resolving tool references for that agent
