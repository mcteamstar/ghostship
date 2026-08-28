## Why

Agents inside crew containers currently have no MCP servers configured — they run with only their built-in kiro-cli tools. Adding MCP servers to a crew today requires manually editing `academy/agents/*.json` files and reinstalling, with no way to vary servers by composition or by agent role within a composition.

Two concrete use cases are blocked by this gap:
- A `spec-ops` crew that can call the Armory (search) or Nexus (project management) during research tasks
- A `research` composition that gives Wraith read-only search tools but not code execution tools

## What Changes

### New: MCP server catalogue (`academy/mcp/`)

A directory of named MCP server definitions. Each file is a JSON object containing the server config (type, url, optional headers). Server names are the filenames without extension.

```
academy/mcp/armory.json
academy/mcp/nexus.json
```

### New: Composition-level MCP declarations (`crews/<name>/manifest.json`)

`manifest.json` gains an optional `mcpServers` array listing server names from the catalogue. All agents in the composition inherit these servers.

Optional `agentMcpServers` map allows per-agent additions or overrides within the composition.

### Modified: Agent JSON files (`academy/agents/*.json`)

Agent files may declare a baseline `mcpServers` block (servers every agent of that persona gets, regardless of composition). Currently empty — this is an additive change.

### Modified: `_copy_agents()` in `transport/server.py`

At crew setup time, resolves the three-level merge for each agent:

1. Agent baseline (`academy/agents/<persona>.json` → `mcpServers`)
2. Composition additions (`crews/<dir>/manifest.json` → `mcpServers`)
3. Inline per-agent overrides (`crews/<dir>/manifest.json` → `agentMcpServers.<persona>`)

Later layers win on key conflicts. Secrets (`${VAR}` references in server configs) are substituted from the transport's environment before being written into the container.

### Modified: `install.sh`

TRN-64's copy-on-install step (once merged) will need to include `academy/mcp/` in the DATA_DIR copy. If TRN-64 is not yet merged, install.sh adds a bind-mount for `academy/mcp/` into the transport container alongside the existing `academy/` mounts.

## Capabilities

### New Capabilities

- MCP server catalogue at `academy/mcp/`
- Composition-level MCP server declarations in `manifest.json`
- Per-agent MCP overrides within a composition

### Modified Capabilities

- `_copy_agents()` — three-level merge at crew setup time
- Agent JSON format — baseline `mcpServers` block supported

## Impact

- `academy/mcp/` — new directory; empty at first, populated as servers are added
- `crews/spec-ops/manifest.json` — gains optional `mcpServers` / `agentMcpServers` fields
- `academy/agents/*.json` — gains optional `mcpServers` baseline (currently empty; no behaviour change until populated)
- `transport/server.py` — `_copy_agents()` extended with merge logic
- `install.sh` — bind-mount or copy step for `academy/mcp/` (depends on TRN-64 merge state)
- `docs/configuration.md` — new section documenting the catalogue format, merge order, and secret substitution
