## Why

The transport exposes a large number of HTTP routes and the MCP server has a full tool schema, but neither is documented in a machine-readable format. An auto-generated OpenAPI 3.x schema served at a well-known endpoint makes the transport self-documenting and gives tooling, clients, and docs a single source of truth.

## What Changes

- Add `GET /openapi.json` to the transport, serving an OpenAPI 3.x schema generated at startup by introspecting the live route table and MCP tool registry
- Cover all transport HTTP routes: MCP, file transfer, dashboard auth, device auth, crew proxy, health, version — with methods, paths, request/response shapes, and auth requirements (Bearer-required vs public)
- Embed MCP tool definitions (tool names, descriptions, input schemas) as a tagged section of the schema, extracted directly from the `@mcp.tool()` decorator registrations
- Add a build-time generation script that writes `openapi.json` to disk for PR diffing and CI artefact capture
- Cross-reference `docs/auth.md`, `docs/caddy.md`, and `docs/dashboard-proxy.md` against the generated schema to ensure accuracy

## Capabilities

### New Capabilities

- `trn-openapi-schema`: OpenAPI 3.x schema endpoint served at `GET /openapi.json`, auto-generated at startup from the live route table and MCP tool registry; auth requirements reflected per-route; build-time generation script for CI diffing

### Modified Capabilities

- `mcp-server`: The transport gains a new discoverable HTTP endpoint (`/openapi.json`) as part of its public surface; auth requirements for the new endpoint must be reflected in the spec

## Impact

- `transport/server.py` — new route handler, startup schema generation logic
- `transport/` — new `openapi.py` module (or equivalent) for schema assembly
- `scripts/` or `Makefile` — build-time generation script
- `docs/auth.md`, `docs/caddy.md`, `docs/dashboard-proxy.md` — cross-reference audit
- No breaking changes; new public route only
