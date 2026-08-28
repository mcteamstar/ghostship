## Why

Agents inside crew containers currently have no MCP servers configured — they run with only their built-in kiro-cli tools. Adding MCP servers to a crew today requires manually editing `academy/agents/*.json` files and reinstalling, with no way to vary servers by composition.

Two concrete use cases are blocked by this gap:
- A `spec-ops` crew that can call the Armory (search) or Nexus (project management) during research tasks
- A `research` composition whose agents get a browser automation tool that `spec-ops` agents don't

## What Changes

### New: MCP server catalogue (`academy/mcp/`)

A directory of named MCP server definitions. Each file is a JSON object containing the server config (type, url or command/args, optional headers). Server names are the filenames without extension.

```
academy/mcp/playwright.json   ← example entry, not wired to any composition by default
academy/mcp/armory.json       ← operator-added example
```

A `README.md` in `academy/mcp/` documents the catalogue convention and format.

### New: Composition-level MCP declarations (`crews/<name>/manifest.json`)

`manifest.json` gains an optional `mcpServers` array listing server names from the catalogue. At crew setup, `_copy_agents()` writes a `~/.kiro/mcp.json` inside the crew container with the resolved configs for all declared servers. Agents in the crew reference them via `@server` in their `tools` list.

```json
{
  "agents": "*",
  "skills": "*",
  "steering": "*",
  "mcpServers": ["armory"]
}
```

### Modified: Agent JSON files (`academy/agents/*.json`)

Agent files may declare their own `mcpServers` map — servers specific to that persona regardless of composition. Agents may also set `includeMcpJson: false` to opt out of the composition-level `mcp.json` entirely. Currently no agent files set either field — this is purely additive.

### Modified: `_copy_agents()` in `transport/server.py`

At crew setup time:
1. Reads `manifest.mcpServers`, resolves each name against `academy/mcp/`, substitutes `${VAR}` references from the transport environment, and writes `~/.kiro/mcp.json` into the crew container
2. Copies agent JSON files as before — agent-level `mcpServers` and `includeMcpJson` fields are preserved as written

### Modified: `install.sh`

The TRN-64 copy step is extended to include `academy/mcp/` → `DATA_DIR/academy/mcp/`. The compose template gains a `${DATA_DIR}/academy/mcp:/mcp:ro` bind-mount so the transport container can read the catalogue at setup time.

## Capabilities

### New Capabilities

- MCP server catalogue at `academy/mcp/`
- Composition-level MCP server declarations in `manifest.json`

### Modified Capabilities

- `_copy_agents()` — writes crew `mcp.json` from manifest declarations
- Agent JSON format — `mcpServers` and `includeMcpJson` fields passed through as-is

## Impact

- `academy/mcp/` — new directory with `README.md` and a `playwright.json` example entry (not active in any composition by default)
- `crews/spec-ops/manifest.json` — gains optional `mcpServers` field (currently undeclared; no behaviour change until populated)
- `academy/agents/*.json` — no changes; `mcpServers` and `includeMcpJson` fields are supported but not set
- `transport/server.py` — `_copy_agents()` extended to write `mcp.json` from manifest
- `install.sh` — rsync step and compose template extended for `academy/mcp/`
- `docs/configuration.md` — new section documenting catalogue format, manifest declaration, and `${VAR}` secret substitution
