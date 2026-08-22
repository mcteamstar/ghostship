# MCP Server Specification

## Purpose

Expose crew orchestration to any MCP client as a single streamable-HTTP server (`ghostship`), covering the tool/resource surface, transport wiring, and discoverability — as distinct from what each tool does internally (see `crew-lifecycle`, `task-orchestration`, `file-transfer`).

## Requirements

### Requirement: Streamable-HTTP MCP transport on a configurable port
The system SHALL serve MCP over streamable HTTP on `PORT` (default `64057`), bound to the host given by `HOST` (default `0.0.0.0` inside the container, published to `127.0.0.1` only by `install.sh`). When `GA_API_KEY` is unset or empty, the transport SHALL preserve the existing network-binding-only trust model. When `GA_API_KEY` is non-empty, every HTTP request to the MCP listener SHALL include `Authorization: Bearer <GA_API_KEY>` and the transport SHALL reject missing, malformed, or incorrect credentials before MCP processing.

#### Scenario: Default port
- **WHEN** the transport process starts with no `PORT` override and `GA_API_KEY` unset or empty
- **THEN** the MCP server listens on `64057` using the `streamable-http` transport in stateless mode and accepts requests as before

#### Scenario: Custom port
- **WHEN** the transport process starts with `PORT=9000`
- **THEN** the MCP server listens on `9000`, and the client-facing URL for registration is `http://localhost:9000/mcp`

#### Scenario: API-key authentication enabled
- **WHEN** the transport process starts with a non-empty `GA_API_KEY` and an MCP request includes exactly one `Authorization` header using the `Bearer` scheme with that configured value
- **THEN** the request reaches the MCP application and can complete normally

#### Scenario: Missing or invalid API key
- **WHEN** the transport process starts with a non-empty `GA_API_KEY` and an MCP request omits, misformats, duplicates, or supplies an incorrect bearer credential
- **THEN** the transport responds with `401 Unauthorized` and `WWW-Authenticate: Bearer`, and the MCP application does not process the request

#### Scenario: Client registration carries the key as a header
- **WHEN** a user registers the server with an MCP client (Kiro CLI, Claude Code, or another streamable-HTTP-capable client) while API-key authentication is enabled
- **THEN** the client points at `http://localhost:<PORT>/mcp` or the configured endpoint and sends `Authorization: Bearer <GA_API_KEY>` on the initialization and subsequent MCP HTTP requests

### Requirement: Companion file server on PORT+1
The system SHALL run a separate Starlette HTTP server on `PORT + 1`, in a background thread independent of the MCP server, exclusively serving the presigned file-transfer routes (`evac`/`supply`).

#### Scenario: File server starts alongside MCP server
- **WHEN** the transport process starts
- **THEN** both the MCP listener on `PORT` and the file-transfer listener on `PORT + 1` are serving before the process is considered ready, and a failure in one does not necessarily block the other since they run on independent threads

### Requirement: Agent roster resource
The system SHALL expose a `transport://agents` MCP resource that lists every agent JSON found in the `/agents` bind-mount, formatted for a client to read before calling `dispatch`.

#### Scenario: Agents present
- **WHEN** `transport://agents` is read and `/agents` contains one or more valid agent JSON files
- **THEN** the response is a plain-text roster with one heading per agent, each showing that agent's `name` and `description` fields

#### Scenario: A malformed agent file
- **WHEN** one file under `/agents` cannot be parsed as JSON
- **THEN** that entry is listed with a placeholder noting it could not be read, rather than failing the whole resource read

#### Scenario: No agents bind-mount
- **WHEN** `/agents` does not exist in the transport container
- **THEN** the resource returns a message stating no agents directory was found, rather than raising an error

### Requirement: Order template resource
The system SHALL expose a `transport://orders` MCP resource that lists every built-in standing-order template — name, description, and full text — formatted for a client to read before calling `captain(action="order", template=<name>, ...)` or before composing an equivalent `message` by hand.

#### Scenario: Templates present
- **WHEN** `transport://orders` is read
- **THEN** the response is a plain-text listing with one heading per template, each showing that template's name, description, and complete body text exactly as `captain(order, template=<name>, ...)` would resolve it

#### Scenario: Reading the resource requires no crew
- **WHEN** `transport://orders` is read
- **THEN** the response does not depend on any crew existing or being reachable, since templates are static, transport-side content — the same property `transport://agents` already has for the agent roster

### Requirement: Client-facing server identity
The system SHALL identify itself to MCP clients as `transport` (server name) while the convention across this project's docs and registration commands is to register the connection under the client-side name `ghostship`.

#### Scenario: Registering with a harness
- **WHEN** a user registers this server with an MCP client (kiro-cli, Claude Code, or any other streamable-HTTP-capable client)
- **THEN** they name the connection `ghostship` and point it at `http://localhost:<PORT>/mcp`, per the README's registration examples

### Requirement: Tool surface covers the full crew lifecycle
The system SHALL expose exactly these tools to MCP clients, grouped and ordered by what they operate on — workspace tools first (`crews`, `launch`, `supply`, `evac`, `nuke`), then agent tools (`captain`, `dispatch`, `schedule`, `steer`, `pickup`, `bridge`) — covering creation, file exchange, teardown, autonomous and manual task orchestration, and blocking task waits.

#### Scenario: Tool discovery
- **WHEN** an MCP client lists tools on the `ghostship` connection
- **THEN** it sees all eleven tools above, in that order, and no others, including `bridge` with the docstring-derived description used for model tool selection
