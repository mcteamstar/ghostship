## 1. Schema Module

- [x] 1.1 Create `transport/openapi.py` with a `generate_schema(routes, public_routes, file_routes, mcp_tools)` function that returns an OpenAPI 3.x dict
- [x] 1.2 Implement route introspection: iterate `routes` and `public_routes` dicts, convert `(method, path)` tuples to OpenAPI path template entries, annotate with `BearerAuth` security or public override
- [x] 1.3 Handle wildcard path conversion: use a hardcoded lookup table mapping known wildcard routes to named OpenAPI path templates (e.g. `/crews/*/ui` → `/crews/{crew_id}/ui`, `/crews/*/api` → `/crews/{crew_id}/api`); do not rely on positional heuristics that would produce generic `{param}` names across all wildcard routes
- [x] 1.4 Add `/health` (public) and file transfer routes from `file_routes` to the schema paths
- [x] 1.5 Implement MCP tool extraction: access `mcp._tool_manager` (or equivalent) synchronously to get tool names, descriptions, and input JSON Schemas
- [x] 1.6 Represent MCP tools as synthetic `POST /mcp/tools/{tool_name}` paths tagged `mcp-tools`, with the tool's input schema as the request body and a note that they are served over the MCP protocol
- [x] 1.7 Populate top-level schema metadata: `openapi: "3.1.0"`, `info` (title, version from `VERSION` file, description), `components.securitySchemes.BearerAuth`

## 2. Transport Integration

- [x] 2.1 In `server.py`, call `openapi.generate_schema(...)` at startup after all routes are defined, before constructing `BearerAuthMiddleware`, and cache the result
- [x] 2.2 Add a `_handle_openapi_get` handler that returns the cached schema as `application/json`
- [x] 2.3 Register `(GET, /openapi.json)` in `public_routes` in the `BearerAuthMiddleware` constructor call

## 3. Build-time Script

- [x] 3.1 Create `scripts/generate_openapi.py` that imports `transport.openapi`, generates the schema, and writes it to `openapi.json` at the repo root (with `--output` override)
- [x] 3.2 Ensure the script is runnable without a running transport process (import-only, no server startup required)
- [x] 3.3 Add the script invocation to CI (e.g. as a step in the test workflow that saves `openapi.json` as a build artefact)

## 4. Tests

- [x] 4.1 Unit test `transport/openapi.py`: given mock route dicts and mock tool list, assert the output is valid OpenAPI 3.x with correct paths, security annotations, and tool entries
- [x] 4.2 Integration test: assert `GET /openapi.json` returns 200 with `Content-Type: application/json` and the body parses as valid JSON
- [x] 4.3 Integration test: assert `GET /openapi.json` returns 200 without an Authorization header even when `GA_API_KEY` is set
- [x] 4.4 Integration test: assert every route key from `routes` and `public_routes` appears in the schema paths object
- [x] 4.5 Integration test: assert all registered MCP tool names appear in the schema under `/mcp/tools/{tool_name}` paths

## 5. Docs Audit

- [x] 5.1 Review `docs/auth.md` against the generated schema — correct any route descriptions, auth requirements, or endpoint paths that are out of date
- [x] 5.2 Review `docs/dashboard-proxy.md` against the generated schema for accuracy on crew proxy routes and auth flow
- [x] 5.3 Review `docs/caddy.md` against the generated schema for accuracy on Caddy-facing routes and port configuration
- [x] 5.4 Add a brief note to `README.md` or `docs/` pointing to `GET /openapi.json` as the authoritative route reference
