# Spec Delta

## MODIFIED Requirements

### Requirement: `GET /api/crews` returns the fleet list
The transport SHALL expose `GET /api/crews` as an HTTP endpoint protected by the `DashboardGate` session mechanism at the Caddy layer (same `gs_session` cookie and `forward_auth` chain as `/` and `/crews/*/ui`). The response SHALL be JSON with `Content-Type: application/json` and SHALL contain the same fleet data returned by the MCP `crews()` tool.

In `BearerAuthMiddleware`, `GET /api/crews` SHALL be listed in `public_routes` — session enforcement is at the Caddy layer, not at the transport bearer layer.

The response shape SHALL be:
```json
{
  "crews": [
    {
      "crew_id": "<string>",
      "container": "<string>",
      "status": "running | stopped",
      "comp": "<string>",
      "composition": "<same value as comp>",
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
      ],
      "captain": {
        "enabled": "<boolean>",
        "schedule": "<string>",
        "current_task_id": "<string | null>"
      } | null
    }
  ],
  "host_memory_available_gb": "<number | null>",
  "active_crews": "<integer>",
  "max_active_crews": "<integer>"
}
```

`comp` SHALL be the canonical crew comp name. `composition` SHALL be a same-value compatibility alias during the rollback window. Legacy-only persisted records SHALL resolve `comp` from `composition`; if both persisted fields differ, `comp` SHALL be authoritative, the mismatch SHALL be logged, and the response SHALL emit both fields with the authoritative value.

#### Scenario: Authenticated request returns fleet JSON
- **WHEN** `GET /api/crews` is requested with a valid `gs_session` cookie
- **THEN** Caddy's `forward_auth` check passes and the transport returns HTTP 200 with `Content-Type: application/json`
- **THEN** the response body matches the schema above

#### Scenario: Unauthenticated request is redirected to login
- **WHEN** `GET /api/crews` is requested without a valid `gs_session` cookie
- **THEN** Caddy's `forward_auth` call returns a redirect to `/dashboard/login`

#### Scenario: Empty fleet returns valid response
- **WHEN** no crews are registered and `GET /api/crews` is called
- **THEN** the response is HTTP 200 with `{"crews": [], "active_crews": 0, ...}`

#### Scenario: Crew response exposes canonical comp and equal alias
- **WHEN** a crew is launched with `comp="spec-ops"` and `GET /api/crews` is called
- **THEN** its entry includes `"comp": "spec-ops"` and `"composition": "spec-ops"`

#### Scenario: Legacy persisted record resolves comp from composition
- **WHEN** a persisted crew record contains only `"composition": "worker"`
- **THEN** the response includes `"comp": "worker"` and `"composition": "worker"`

#### Scenario: Mismatched persisted fields normalize to comp
- **WHEN** a persisted crew record contains `"comp": "spec-ops"` and `"composition": "worker"`
- **THEN** the mismatch is logged and the response includes both fields as `"spec-ops"`

#### Scenario: REST and MCP comp values match
- **WHEN** `GET /api/crews` and the MCP `crews()` tool are called for the same fleet state
- **THEN** both responses report the same `comp` and `composition` values for every crew
