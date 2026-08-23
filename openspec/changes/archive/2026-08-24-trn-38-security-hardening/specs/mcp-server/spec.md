## MODIFIED Requirements

### Requirement: Streamable-HTTP MCP transport on a configurable port
The system SHALL serve MCP over streamable HTTP on `PORT` (default `64057`), bound to the host given by `HOST` (default **`0.0.0.0`** inside a container). For containerised installs, host-side isolation is provided by `install.sh` publishing the port as `-p "127.0.0.1:PORT:PORT"`, making it unreachable from other network hosts regardless of the container-internal bind. Operators running the transport directly (non-containerised) who need loopback-only binding SHALL set `HOST=127.0.0.1` explicitly. When `GA_API_KEY` is unset or empty, the transport SHALL preserve the existing trust model. When `GA_API_KEY` is non-empty, every HTTP request to the MCP listener SHALL include `Authorization: Bearer <GA_API_KEY>` and the transport SHALL reject missing, malformed, or incorrect credentials before MCP processing.

#### Scenario: Default bind address for containerised install

- **WHEN** the transport starts inside a container without a `HOST` override and `install.sh` published the port as `-p "127.0.0.1:PORT:PORT"`
- **THEN** the MCP server is reachable only from localhost on the host, not from other network hosts

#### Scenario: Non-containerised loopback binding

- **WHEN** the transport starts with `HOST=127.0.0.1`
- **THEN** the MCP server listens on loopback only and is not reachable from the local network

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
- **WHEN** a user registers the server with an MCP client while API-key authentication is enabled
- **THEN** the client points at `http://localhost:<PORT>/mcp` and sends `Authorization: Bearer <GA_API_KEY>` on initialization and subsequent MCP HTTP requests
