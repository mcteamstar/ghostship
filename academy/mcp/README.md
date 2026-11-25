# MCP Server Catalogue

This directory is the **MCP server catalogue** for Ghost Academy. Each file is
a named server definition. The filename without the `.json` extension is the
server name used to reference the server from a comp manifest.

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
  "args": [
    "--yes",
    "@playwright/mcp@latest",
    "--executable-path",
    "/usr/bin/chromium",
    "--headless",
    "--no-sandbox"
  ],
  "env": {
    "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"
  }
}
```

The `spec-ops` image installs Debian Chromium at `/usr/bin/chromium`; this
image-owned path remains visible when the crew home is mounted as a volume.
`--no-sandbox` disables Chromium's nested browser sandbox, which cannot start
inside the existing crew/Codex sandbox; the outer crew container restrictions
remain in place.

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
KiroCrew 0.5.0 from pooling auth-bearing HTTP servers. You do not need to
declare `poolable: false` in the catalogue file itself.

## Wiring a server into a comp

Add the server name to the `mcpServers` array in
`crews/<comp>/manifest.json`:

```json
{
  "agents": "*",
  "skills": "*",
  "steering": "*",
  "mcpServers": ["armory", "nexus"]
}
```

At crew setup time, Academy resolves each name against this catalogue,
substitutes `${VAR}` references, and stages the entries in
`.agents/mcp/servers.json`. `.agents/setup` wires them into the selected
harness's native configuration. Academy also copies each selected server into
the `mcpServers` map of personas whose `tools` list references `@<name>` (or
grants all tools with `"*"`). This puts MCP servers in ACP session arrays,
including Codex sessions. A persona's own same-named entry takes precedence.

## Empty catalogue

An empty catalogue (no JSON files) is valid. No `.agents/mcp/servers.json` is
staged, and agents receive no composition-level MCP entries.

## Per-agent mcpServers

Individual agent JSON files in `academy/agents/` may also declare a
`mcpServers` map for servers specific to that agent regardless of the
comp. Academy preserves those entries and gives them precedence over a
same-named comp entry. See `docs/configuration.md` for the full setup flow.
