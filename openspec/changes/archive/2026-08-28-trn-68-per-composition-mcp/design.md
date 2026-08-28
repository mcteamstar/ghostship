## Context

See proposal.md — Why for motivation.

`_copy_agents()` in `transport/server.py` already copies agent JSON files from `/agents` (bind-mounted from `DATA_DIR/academy/agents/`) into each crew container at `~/.kiro/agents/`. It reads the composition manifest to select which agents to copy, then uses `container_archive_put` to write them into the container.

KiroCrew's kiro-cli resolves MCP server references in two ways:
1. **Agent-level** — `mcpServers` map in the agent's own JSON (`~/.kiro/agents/<name>.json`)
2. **Global** — `~/.kiro/mcp.json` — a workspace-level catalogue consulted for any `@server` tool reference not found in the agent's own `mcpServers`. Agents opt out via `includeMcpJson: false`.

Ghostship currently writes no `mcp.json` into crew containers. Agent JSON files have no `mcpServers` block. All agents run with zero MCP servers beyond kiro-cli's built-ins.

## Goals / Non-Goals

**Goals:**
- Composition manifests can declare MCP servers that become available to the whole crew via `mcp.json`
- Individual agent JSON files can declare agent-specific `mcpServers` (agents that need servers the composition doesn't provide, or that want to opt out of the global pool)
- A server catalogue (`academy/mcp/`) keeps server definitions DRY — manifests and agent files reference names, not inline configs
- Secrets (`${VAR}` references in server URLs or headers) are substituted from the transport's environment at crew setup time, never stored in committed files

**Non-Goals:**
- Per-agent override mechanism in the manifest (composition → mcp.json, agent JSON → agent-specific; that's the full model for now)
- Inline server configs in manifest.json (catalogue-only, to prevent secrets in committed files)
- Live reload of MCP config without reinstall
- Any changes to KiroCrew internals

## Decisions

### D1: Two-layer model matching KiroCrew's own resolution

**Decision:** Ghostship uses KiroCrew's existing two-layer model directly:
- Composition level → `~/.kiro/mcp.json` in the crew container
- Agent level → `mcpServers` block in each agent's JSON

**Rationale:** KiroCrew already resolves these two layers in order. Building a parallel inheritance system would fight the tool resolution logic and create a maintenance burden. Working with the existing model means ghostship only needs to write the right files into the right places.

**Alternative considered:** Three-layer model with manifest-level per-agent overrides. Rejected — adds complexity for a use case that can be served by writing a variant agent JSON file (e.g. `banshee-research.json`). Can be added later if a real need emerges.

### D2: Server catalogue at `academy/mcp/`

**Decision:** Each MCP server definition lives as a named JSON file in `academy/mcp/<name>.json`. Manifests and agent files reference server names; `_copy_agents()` resolves them against the catalogue.

**Rationale:** Keeps definitions DRY across compositions. A server URL change requires editing one file, not hunting through manifests. Prevents inline configs (which is how secrets end up in committed files).

**Catalogue entry format** (same as kiro-cli `mcpServers` value):
```json
{
  "type": "streamable-http",
  "url": "http://armory.penguin-piano.ts.net/mcp"
}
```
Or with auth headers:
```json
{
  "type": "streamable-http",
  "url": "http://nexus.example.com/mcp",
  "headers": {
    "Authorization": "Bearer ${NEXUS_API_KEY}"
  }
}
```

### D3: `${VAR}` substitution at setup time

**Decision:** Any `${VAR}` reference in any string value in a catalogue entry is substituted from the transport container's environment at the point `_copy_agents()` writes the crew's `mcp.json`.

**Rationale:** Secrets must never be written into committed files. The transport already has access to secrets via environment variables (e.g. `GA_API_KEY` pattern). This is the natural injection point.

**Behaviour on missing variable:** Log a warning and write the literal `${VAR}` string — do not fail the crew setup. A missing secret degrades gracefully (the server will auth-fail at call time) rather than blocking the crew from starting.

### D4: `academy/mcp/` added to install.sh copy step

**Decision:** TRN-64's rsync copy step in `install.sh` is extended to include `academy/mcp/` → `DATA_DIR/academy/mcp/`. A new bind-mount entry in the compose template exposes it to the transport container at `/mcp`.

**Rationale:** Follows the established TRN-64 pattern — academy content is snapshotted at install time, not read from the live repo at runtime.

### D5: Missing catalogue entry behaviour

**Decision:** If a manifest or agent JSON references a server name not found in `academy/mcp/`, log a warning and skip that server — do not fail crew setup.

**Rationale:** A misconfigured server name should not prevent a crew from starting. The warning gives the operator enough signal to fix it. Consistent with KiroCrew's own behaviour (dangling `@server` references are silently dropped at mount time).

### D6: `poolable: false` for servers with env declarations

**Decision:** Any catalogue entry that contains a `headers` block (or any field that varies per-session) has `poolable: false` automatically set when written into `mcp.json`. This is not required by the operator in the catalogue file.

**Rationale:** KiroCrew 0.4.0 only pools stdio servers without env/headers. An HTTP server with auth headers must not be pooled — the header value is the same for all uses, but the flag prevents unexpected pooling behaviour if KiroCrew's pooling logic changes.

## Risks / Trade-offs

- **[Risk] Agent declares a server name also in the composition pool** → Both appear in `mcp.json` and agent `mcpServers`. kiro-cli uses the agent's own `mcpServers` entry first; the `mcp.json` entry is shadowed. No error. Document as expected behaviour.
- **[Risk] `${VAR}` substitution at setup time means secrets are written into the crew container** → Mitigated by the fact that crew containers are ephemeral, rootless, and isolated. The secret is not written to any committed file or the host DATA_DIR.
- **[Risk] `academy/mcp/` starts empty — no servers ship by default** → Intentional. Operators populate it for their deployment. Document with examples.

## Open Questions

None — all decisions needed to proceed are resolved above.
