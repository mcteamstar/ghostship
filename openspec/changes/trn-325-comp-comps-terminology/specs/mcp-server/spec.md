# Spec Delta

## MODIFIED Requirements

### Requirement: crews() response shape
The `crews()` MCP tool SHALL return a JSON object with a top-level `crews` array. Each crew entry SHALL include:
- `crew_id` (string)
- `container` (string)
- `status` (string: `"running"` | `"stopped"`)
- `comp` (string) — the canonical crew comp name
- `composition` (string) — a same-value compatibility alias during the rollback window
- `created_at` (ISO 8601 string)
- `last_task_at` (ISO 8601 string | null)
- `uptime_secs` (integer | null) — present for running crews and absent or null for stopped crews
- `gateway_healthy` (boolean)
- `crew_image_version` (string)
- `dashboard_url` (string | null)
- `policy_version` (integer)
- `agents` (array) — one entry per tracked crew task, each containing `task_id` (string), `agent` (string), `done` (boolean), and `elapsed_secs` (number)

The `agents` entries SHALL NOT include `last_tool`. The top-level response SHALL also include `host_memory_available_gb`, `active_crews`, and `max_active_crews`. When persisted data has only `composition`, the response SHALL resolve `comp` from that value. When persisted `comp` and `composition` differ, `comp` SHALL be authoritative, the mismatch SHALL be logged, and the response SHALL emit both fields with the authoritative value.

#### Scenario: crews() omits last_tool from agent entries
- **WHEN** `crews()` is called and one or more agents are listed for a crew
- **THEN** each agent entry contains `task_id`, `agent`, `done`, and `elapsed_secs`, and does not contain `last_tool`

#### Scenario: running crew includes uptime_secs
- **WHEN** `crews()` is called and a crew has `status == "running"`
- **THEN** that crew's entry includes an `uptime_secs` integer reflecting seconds since its container started

#### Scenario: stopped crew omits uptime_secs
- **WHEN** `crews()` is called and a crew has `status == "stopped"`
- **THEN** its `uptime_secs` is absent or null

#### Scenario: last_task_at populated when tasks have been dispatched
- **WHEN** at least one task has been dispatched to a crew
- **THEN** that crew's `last_task_at` is an ISO 8601 timestamp for the most recent dispatch

#### Scenario: last_task_at is null for crews with no task history
- **WHEN** a crew has never had a task dispatched
- **THEN** its `last_task_at` is null

#### Scenario: Crew entry exposes comp and equal compatibility alias
- **WHEN** a crew was launched with `comp="spec-ops"`
- **THEN** its entry includes `"comp": "spec-ops"` and `"composition": "spec-ops"`

#### Scenario: Legacy persisted record resolves comp from composition
- **WHEN** a persisted crew record contains only `"composition": "spec-ops"`
- **THEN** the response includes `"comp": "spec-ops"` and `"composition": "spec-ops"`

#### Scenario: Mismatched persisted fields normalize to comp
- **WHEN** a persisted crew record contains `"comp": "spec-ops"` and `"composition": "worker"`
- **THEN** the mismatch is logged and the response includes both fields as `"spec-ops"`
