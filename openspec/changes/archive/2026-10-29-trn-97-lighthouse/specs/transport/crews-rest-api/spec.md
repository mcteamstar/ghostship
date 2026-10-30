## Purpose

Exposes fleet state as a first-class bearer-gated REST endpoint at `GET /api/crews`,
making the data available to browser clients and external integrations without
requiring an MCP session.

## ADDED Requirements

### Requirement: `GET /api/crews` returns the fleet list

The transport SHALL expose `GET /api/crews` as an HTTP endpoint protected by the
`DashboardGate` session mechanism at the Caddy layer (same `gs_session` cookie and
`forward_auth` chain as `/` and `/crews/*/ui`). The response SHALL be JSON with
`Content-Type: application/json` and SHALL contain the same fleet data returned by
the MCP `crews()` tool.

In `BearerAuthMiddleware`, `GET /api/crews` SHALL be listed in `public_routes` —
session enforcement is at the Caddy layer, not at the transport bearer layer.

The response shape SHALL be:
```json
{
  "crews": [
    {
      "crew_id": "<string>",
      "container": "<string>",
      "status": "running | stopped",
      "composition": "<string>",
      "acp_backend": "<string>",
      "created_at": "<iso8601 | null>",
      "last_task_at": "<iso8601 | null>",
      "gateway_healthy": "<boolean>",
      "crew_image_version": "<string>",
      "enrolled_agents": ["<string>"],
      "dashboard_url": "<string | null>",
      "uptime_secs": "<integer | null>",
      "agents": [
        {
          "task_id": "<string>",
          "agent": "<string>",
          "done": "<boolean>",
          "elapsed_secs": "<integer>"
        }
      ]
    }
  ],
  "host_memory_available_gb": "<number | null>",
  "active_crews": "<integer>",
  "max_active_crews": "<integer>"
}
```

#### Scenario: Authenticated request returns fleet JSON
- **WHEN** `GET /api/crews` is requested with a valid `gs_session` cookie
- **THEN** Caddy's `forward_auth` check passes and the transport returns HTTP 200
  with `Content-Type: application/json`
- **THEN** the response body matches the schema above

#### Scenario: Unauthenticated request is redirected to login
- **WHEN** `GET /api/crews` is requested without a valid `gs_session` cookie
- **THEN** Caddy's `forward_auth` call returns a redirect to `/dashboard/login`

#### Scenario: Empty fleet returns valid response
- **WHEN** no crews are registered and `GET /api/crews` is called
- **THEN** the response is HTTP 200 with `{"crews": [], "active_crews": 0, ...}`

### Requirement: `GET /api/crews` shares data assembly with the MCP `crews()` tool

The data returned by `GET /api/crews` SHALL be assembled by the same code path as
the MCP `crews()` tool. The two surfaces SHALL NOT diverge in their representation
of fleet state. A shared helper function SHALL be the single source of fleet data
assembly; both the REST handler and the MCP tool SHALL call it.

#### Scenario: REST and MCP return identical crew records
- **WHEN** `GET /api/crews` and the MCP `crews()` tool are called at the same moment
- **THEN** the `crews` array in both responses contains the same crew entries with
  the same field values
