## Context

The transport's full HTTP surface is defined in two places:

1. `BearerAuthMiddleware` — receives `routes` (Bearer-required) and `public_routes` (unauthenticated) as `{(method, path): handler}` dicts injected at construction in `server.py`. File routes are a separate Starlette app passed as `file_app`. `/health` bypasses the middleware via a hard-coded `_PUBLIC_PATHS` set.
2. `@mcp.tool()` decorators — register tools on the `FastMCP` instance (`mcp`) in `server.py`. The FastMCP SDK exposes tool metadata (name, description, input schema) via `await mcp.get_tools()`.

Both sources are available at import/startup time and require no running crew. The route dicts are keyed by `(method, path)` tuples, making them easy to iterate.

## Goals / Non-Goals

**Goals:**
- Serve a valid OpenAPI 3.x JSON document at `GET /openapi.json` at startup
- Cover all HTTP routes with methods, paths, descriptions, and auth annotations
- Include MCP tool definitions (name, description, input schema) as a tagged group
- Provide a build-time generation script for CI diff capture

**Non-Goals:**
- Full request/response JSON schema for every route body (route bodies are complex and mostly MCP-internal; a best-effort shape is acceptable)
- Interactive Swagger/Redoc UI (serving the JSON document only)
- Runtime schema invalidation or hot-reload when routes change
- WebSocket routes (the `/crews/*/ui` WS proxy is documented as a note, not a full WS schema entry)

## Decisions

### 1. New `transport/openapi.py` module for schema assembly

Extract schema generation into a dedicated `transport/openapi.py` module rather than inlining it in `server.py`. `server.py` passes the route dicts and `mcp` instance to the module at startup; the module returns a dict that `server.py` serves directly.

**Alternative considered:** Inline in `server.py`. Rejected — `server.py` is already very large (~3700 lines); a self-contained module is easier to test and maintain.

### 2. Static generation at startup, served from memory

Generate the schema once at startup (when all routes and tools are registered) and cache it as a module-level dict. The `/openapi.json` handler returns the cached dict serialised to JSON on every request.

**Alternative considered:** Generate on every request. Rejected — unnecessary overhead; the route table and tool registry don't change at runtime.

**Alternative considered:** Build-time only (committed file). Rejected — a committed file can drift from the actual routes; startup generation is always accurate.

### 3. Route introspection via the injected dicts

Walk `routes` and `public_routes` at startup before constructing `BearerAuthMiddleware`, then pass them to `openapi.py`. File routes come from the `file_routes` list. Health comes from `_PUBLIC_PATHS`.

The route key is `(method, path)` where path may contain `*` wildcards (e.g. `/crews/*/ui`). A hardcoded lookup table maps known wildcard routes to named OpenAPI path templates (e.g. `/crews/*/ui` → `/crews/{crew_id}/ui`, `/crews/*/api` → `/crews/{crew_id}/api`). This avoids a positional heuristic that would produce generic `{param}` names across all wildcard routes sharing the same structure.

### 4. MCP tools via FastMCP's tool registry

FastMCP exposes registered tools at `mcp._tool_manager.list_tools()` (or the equivalent async `get_tools()` coroutine). Call this synchronously at startup (tools are registered at import time, not lazily) by accessing the internal tool manager directly rather than calling the async method. Each tool yields name, description, and a JSON Schema dict for its input model.

**Alternative considered:** Parse `@mcp.tool()` decorators via AST or `inspect`. Rejected — fragile and redundant when the SDK already stores the metadata.

### 5. MCP tools represented as synthetic POST routes under `/mcp/tools/{tool_name}`

Represent MCP tools as `POST /mcp/tools/{tool_name}` paths in the schema, tagged `mcp-tools`, with the tool's input schema as the request body. This is a documentation convention, not a real route — the path description notes it is served over the MCP protocol.

**Alternative considered:** A single `POST /mcp` entry with a discriminated union body. Rejected — obscures individual tool definitions and makes the schema less useful for documentation tooling.

### 6. `GET /openapi.json` is a public route (no auth required)

Register `/openapi.json` in `public_routes` so it is accessible without a bearer token, consistent with `/version` and `/health`. Schema content is not sensitive.

### 7. Build-time script as `scripts/generate_openapi.py`

A standalone script imports `transport.openapi`, generates the schema, and writes it to `openapi.json` at the repo root (or a path given by `--output`). Used in CI to capture the schema as an artefact and surface diffs in PRs.

The script must be runnable without a running transport process — it imports the module directly and calls the generation function, not the HTTP endpoint.

## Risks / Trade-offs

- **FastMCP internal API** — accessing `mcp._tool_manager` is semi-private. If FastMCP adds a public `list_tools()` sync API in a future version, we should migrate. Risk is low: the tool manager has been stable across recent upgrades. Mitigation: wrap the access in a helper in `openapi.py` so there's one place to update.
- **Route wildcard conversion** — the lookup table covers all known wildcard routes at time of writing. New wildcard routes added in future won't appear with named params automatically — they'll fall through to a generic `{param}` or be omitted until the table is updated. Mitigation: the build-time script test asserts all route keys appear in the schema, which will catch any unmapped new wildcards in CI.
- **Schema drift in docs** — `docs/auth.md`, `docs/caddy.md`, and `docs/dashboard-proxy.md` may describe routes inconsistently. The cross-reference audit is a manual step; it doesn't prevent future drift. Mitigation: note in the docs that `/openapi.json` is the authoritative reference.

## Migration Plan

- New file `transport/openapi.py` — no existing code changed
- `transport/server.py` — add one route handler and one call to `openapi.py` at startup; register `/openapi.json` in `public_routes`
- `scripts/generate_openapi.py` — new file, no existing scripts affected
- No breaking changes; no migration required for existing clients
