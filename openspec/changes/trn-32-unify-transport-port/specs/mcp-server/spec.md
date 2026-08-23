## MODIFIED Requirements

### Requirement: Transport exposes a single port

The transport SHALL bind to a single port for all operations: MCP, REST, and
file transfer. A second file-server port SHALL NOT exist. The single port SHALL
be configurable via `GA_PORT` (default 8000).

#### Scenario: All operations on one port
- **WHEN** a client connects to the transport's single port
- **THEN** MCP (`/mcp`), REST (`/login`, `/logout`, `/health`, `/version`), and file transfer (`/files/*`) are all available at that port

#### Scenario: No second port
- **WHEN** the transport starts
- **THEN** only one port is bound; no service listens on `PORT+1`

### Requirement: Single public URL configuration

The transport SHALL accept a single `GA_PUBLIC_URL` environment variable as the
base URL for all externally-reachable endpoints, replacing the previous split
between `GA_MCP_PUBLIC_URL` and `GA_FILE_PUBLIC_URL`. Presigned file URLs
(supply and evac) SHALL use `GA_PUBLIC_URL` as their base.

#### Scenario: Presigned URLs use GA_PUBLIC_URL
- **WHEN** the Admiral calls `evac()` or `supply()`
- **THEN** the returned URL uses `GA_PUBLIC_URL` as its base (e.g. `https://my-host.example.com/files/...`)

#### Scenario: Legacy vars ignored
- **WHEN** `GA_MCP_PUBLIC_URL` or `GA_FILE_PUBLIC_URL` are set but `GA_PUBLIC_URL` is not
- **THEN** the transport logs a deprecation warning and falls back to `GA_MCP_PUBLIC_URL` for backward compatibility
