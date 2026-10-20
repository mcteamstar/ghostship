# Spec Delta

## MODIFIED Requirements

### Requirement: Composition manifest declares crew-level MCP servers
The composition `manifest.json` MAY include a `mcpServers` array of server names. Each name SHALL be resolved against the `academy/mcp/` catalogue. At crew setup, `AcademyLoader` SHALL stage the resolved configs into `/home/kirocrew/.agents/mcp/` and then call `.agents/setup <backend>`, which writes the MCP config to the backend-native location and format (e.g. `~/.kiro/mcp.json` for kiro, the `mcpServers` section of `~/.claude.json` for claude).

#### Scenario: Manifest declares servers and crew mcp.json is written
- **WHEN** `crews/spec-ops/manifest.json` contains `{"mcpServers": ["armory", "nexus"]}` and the backend is kiro
- **THEN** after setup completes, the crew container has `~/.kiro/mcp.json` with entries for `armory` and `nexus`

#### Scenario: kiro backend receives mcp.json
- **WHEN** `manifest.json` declares `mcpServers` and the crew's backend is `kiro`
- **THEN** after setup completes, the crew container has `~/.kiro/mcp.json` with entries for all resolved server names

#### Scenario: claude backend receives mcpServers in .claude.json
- **WHEN** `manifest.json` declares `mcpServers` and the crew's backend is `claude`
- **THEN** after setup completes, the crew container's `~/.claude.json` contains the resolved server entries under `mcpServers`

#### Scenario: Manifest declares no mcpServers key
- **WHEN** `manifest.json` has no `mcpServers` key
- **THEN** no MCP config is staged or written into the crew container by the composition step

#### Scenario: Unknown server name is skipped with a warning
- **WHEN** `manifest.json` declares a server name that has no matching file in `academy/mcp/`
- **THEN** `AcademyLoader` logs a warning naming the missing entry and skips it; crew setup continues and the remaining servers are written normally
