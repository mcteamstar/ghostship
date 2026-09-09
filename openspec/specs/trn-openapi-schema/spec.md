# Transport OpenAPI Schema Specification

## Purpose

Expose a machine-readable OpenAPI 3.x schema for all transport HTTP routes and MCP tools, served at a well-known endpoint and generated as a build-time artefact, so that clients, tooling, and documentation have a single source of truth for the transport's public surface.

## Requirements

### Requirement: OpenAPI schema served at GET /openapi.json

The transport SHALL serve an OpenAPI 3.x–compliant JSON document at `GET /openapi.json`. The document SHALL be generated at startup by introspecting the live route table and MCP tool registry, and SHALL remain static for the lifetime of the process.

#### Scenario: Schema is available at startup

- **WHEN** the transport process starts
- **THEN** `GET /openapi.json` returns `200 OK` with `Content-Type: application/json` and a valid OpenAPI 3.x JSON body

#### Scenario: Schema requires no authentication

- **WHEN** `GA_API_KEY` is configured and a request to `GET /openapi.json` omits the bearer token
- **THEN** the response is `200 OK` — the schema endpoint SHALL NOT require authentication

#### Scenario: Schema content matches live route table

- **WHEN** `GET /openapi.json` is fetched
- **THEN** every HTTP route registered in `BearerAuthMiddleware` (both authenticated routes and public routes) appears in the schema's `paths` object with the correct HTTP method, path, and auth annotation

### Requirement: Schema covers all transport HTTP routes

The OpenAPI schema SHALL include every HTTP route exposed by the transport, covering:
- MCP endpoint (`/mcp`)
- Authentication routes (`/login`, `/logout`)
- Dashboard auth routes (`/dashboard/login`, `/dashboard/logout`, `/dashboard/auth`)
- Crew proxy routes (`/crews/{crew_id}/ui`, `/crews/{crew_id}/api`, `/crews/{crew_id}/dashboard`)
- Health and version routes (`/health`, `/version`)
- File transfer routes (`/files/{crew_id}/{path}`)
- Schema route itself (`/openapi.json`)

Each route entry SHALL include the HTTP method(s), a brief description, and whether the route requires Bearer authentication.

#### Scenario: Authenticated routes are annotated in the schema

- **WHEN** `GET /openapi.json` is fetched
- **THEN** routes that require a Bearer token include a `security` array referencing a `BearerAuth` security scheme defined in the schema's `components.securitySchemes`

#### Scenario: Public routes carry no security requirement

- **WHEN** `GET /openapi.json` is fetched
- **THEN** routes declared in `public_routes` (e.g. `/version`, `/dashboard/login`) have no `security` array, or an explicit empty `security: []` override

### Requirement: Schema includes MCP tool definitions

The OpenAPI schema SHALL include a section documenting the MCP tool surface. Each registered MCP tool SHALL appear with its name, description, and JSON Schema input definition, extracted directly from the `@mcp.tool()` decorator registrations.

The MCP tools MAY be represented as a synthetic route (e.g. `POST /mcp/tools/{tool_name}`) or as a dedicated tag grouping — the representation SHALL be consistent and clearly labelled as the MCP tool surface.

#### Scenario: All registered MCP tools appear in the schema

- **WHEN** `GET /openapi.json` is fetched
- **THEN** every tool registered via `@mcp.tool()` appears in the schema with a name, description, and input schema

#### Scenario: MCP tool input schemas match registered definitions

- **WHEN** `GET /openapi.json` is fetched and a tool has a typed input model
- **THEN** the schema's representation of that tool's inputs matches the JSON Schema produced by the tool's Pydantic/TypedDict model, with no manual transcription

### Requirement: Build-time schema generation script

A script SHALL be provided that introspects the transport and writes `openapi.json` to a configurable output path (defaulting to the repository root). The script SHALL be runnable in CI to capture the schema as a build artefact and enable diff-based review in PRs.

#### Scenario: Script produces a valid OpenAPI document

- **WHEN** the generation script is executed against the transport module
- **THEN** it exits with code 0 and writes a valid OpenAPI 3.x JSON document to the specified output path

#### Scenario: Schema diff is visible in CI

- **WHEN** a PR modifies the transport's route table or an MCP tool definition
- **THEN** the CI run regenerates `openapi.json`, and the diff is visible in the PR as a changed file
