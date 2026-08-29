# MCP Server Catalogue

This directory is the **MCP server catalogue** for Ghost Academy. Each file is
a named server definition. The filename without the `.json` extension is the
server name used to reference the server from a composition manifest.

## File naming

```
academy/mcp/<name>.json
```

- `name` is the server reference used in `manifest.json → mcpServers`
- Names should be lowercase, using hyphens to separate words (e.g. `armory`,
  `nexus`, `playwright`)

## JSON format

Each file is a JSON object conforming to the kiro-cli `mcpServers` entry format.
At minimum a `type` field and either a `url` (HTTP/SSE) or `command` (stdio)
field are required.

### HTTP server (streamable-http or sse)

```json
{
  "type": "streamable-http",
  "url": "http://armory.example.com/mcp"
}
```

### HTTP server with auth header

```json
{
  "type": "streamable-http",
  "url": "http://nexus.example.com/mcp",
  "headers": {
    "Authorization": "Bearer ${NEXUS_API_KEY}"
  }
}
```

### Stdio server

```json
{
  "type": "stdio",
  "command": "npx",
  "args": ["@playwright/mcp@latest"]
}
```

## `${VAR}` substitution

Any `${VAR}` reference in a string value is substituted from the transport
container's environment at the point `_copy_agents()` writes the crew's
`~/.kiro/mcp.json`. This is the mechanism for injecting secrets (API keys,
tokens) without committing them to the repository.

- If the variable is set: the value is substituted in the written entry.
- If the variable is **not** set: a warning is logged, the literal
  `${VAR}` string is written, and crew setup continues. The server will
  auth-fail at call time but does not block the crew from starting.

Set secrets in the transport container's environment by passing them through
`install.sh` configuration or environment variables that the transport
container inherits.

## `poolable: false` — automatic for servers with `headers`

Any catalogue entry containing a `headers` field has `poolable: false`
automatically added when written into a crew's `mcp.json`. This prevents
KiroCrew 0.4.0 from pooling auth-bearing HTTP servers. You do not need to
declare `poolable: false` in the catalogue file itself.

## Wiring a server into a composition

Add the server name to the `mcpServers` array in
`crews/<composition>/manifest.json`:

```json
{
  "agents": "*",
  "skills": "*",
  "steering": "*",
  "mcpServers": ["armory", "nexus"]
}
```

At crew setup time, `_copy_agents()` resolves each name against this catalogue,
substitutes `${VAR}` references, and writes `~/.kiro/mcp.json` inside the crew
container. Agents reference servers via `@<name>` in their `tools` list.

## Empty catalogue

An empty catalogue (no JSON files) is valid. No `mcp.json` is written into
crew containers, and agents have access only to their built-in tools and any
`mcpServers` declared in their own agent JSON.

## Per-agent mcpServers

Individual agent JSON files in `academy/agents/` may also declare a
`mcpServers` map for servers specific to that agent regardless of the
composition. An agent may set `includeMcpJson: false` to opt out of the
composition-level `mcp.json` entirely. See `docs/configuration.md` for
the full two-layer resolution model.
