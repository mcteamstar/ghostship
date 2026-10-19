## MODIFIED Requirements

### Requirement: Streamable-HTTP MCP transport on a configurable port
The system SHALL serve MCP over streamable HTTP on port `64057` inside the transport container, listening on the fixed in-container address `0.0.0.0` so that `ga-portal` can reach it over the internal Podman network. The transport's listen address SHALL NOT be read from `HOST`. Host-side exposure SHALL be determined solely by the address and port `ga-portal` publishes on (`HOST`, default `127.0.0.1`, and `PORT`, default `64057`). The transport container SHALL publish no host port. When `GA_API_KEY` is unset or empty, the transport SHALL preserve the existing trust model. When `GA_API_KEY` is non-empty, every HTTP request to the MCP listener SHALL include `Authorization: Bearer <GA_API_KEY>` and the transport SHALL reject missing, malformed, or incorrect credentials before MCP processing.

#### Scenario: Default bind address for containerised install
- **WHEN** the transport starts inside a container with `HOST` unset
- **THEN** the MCP server is reachable through `ga-portal` only from localhost on the host, not from other network hosts

#### Scenario: Non-containerised loopback binding
- **WHEN** the operator sets `HOST=127.0.0.1`
- **THEN** the MCP server is reachable through `ga-portal` on host loopback only and not from the local network, while the transport itself still listens on `0.0.0.0` inside its container so `ga-portal` can reach it at `ga-transport:64057`

#### Scenario: Default port
- **WHEN** the transport process starts with no `PORT` override and `GA_API_KEY` unset or empty
- **THEN** the MCP server listens on `64057` using the `streamable-http` transport in stateless mode and accepts requests as before

#### Scenario: Custom port
- **WHEN** the operator sets `PORT=9000`
- **THEN** `ga-portal` publishes on host port `9000`, the transport continues to listen on `64057` internally, and the client-facing URL for registration is `http://localhost:9000/mcp`

#### Scenario: API-key authentication enabled
- **WHEN** the transport process starts with a non-empty `GA_API_KEY` and an MCP request includes exactly one `Authorization` header using the `Bearer` scheme with that configured value
- **THEN** the request reaches the MCP application and can complete normally

#### Scenario: Missing or invalid API key
- **WHEN** the transport process starts with a non-empty `GA_API_KEY` and an MCP request omits, misformats, duplicates, or supplies an incorrect bearer credential
- **THEN** the transport responds with `401 Unauthorized` and `WWW-Authenticate: Bearer`, and the MCP application does not process the request

#### Scenario: Client registration carries the key as a header
- **WHEN** a user registers the server with an MCP client while API-key authentication is enabled
- **THEN** the client points at `http://localhost:<PORT>/mcp` and sends `Authorization: Bearer <GA_API_KEY>` on initialization and subsequent MCP HTTP requests
