## MODIFIED Requirements

### Requirement: crews() response shape

The `crews()` MCP tool SHALL return a JSON object with a top-level `crews` array. Each crew entry SHALL include:

- `crew_id` (string)
- `container` (string)
- `status` (string: `"running"` | `"stopped"`)
- `composition` (string)
- `created_at` (ISO 8601 string)
- `last_task_at` (ISO 8601 string | null) — timestamp of the last task dispatched to this crew; null if no task has ever been dispatched
- `uptime_secs` (integer | null) — seconds elapsed since the container started, derived from the container's `StartedAt` timestamp; present only when `status == "running"`, absent (or null) otherwise
- `gateway_healthy` (boolean)
- `crew_image_version` (string)
- `dashboard_url` (string | null)
- `policy_version` (integer)
- `agents` (array) — one entry per task currently tracked for this crew, each containing:
  - `task_id` (string)
  - `agent` (string)
  - `done` (boolean)
  - `elapsed_secs` (number)

The `agents` entries SHALL NOT include a `last_tool` field. `last_tool` is removed from the response.

The top-level response object SHALL also include `host_memory_available_gb`, `active_crews`, and `max_active_crews` as before.

#### Scenario: crews() omits last_tool from agent entries

- **WHEN** `crews()` is called and one or more agents are listed for a crew
- **THEN** each agent entry contains `task_id`, `agent`, `done`, and `elapsed_secs`, and does NOT contain a `last_tool` field

#### Scenario: running crew includes uptime_secs

- **WHEN** `crews()` is called and a crew has `status == "running"`
- **THEN** that crew's entry includes an `uptime_secs` integer reflecting the number of seconds since the container started

#### Scenario: stopped crew omits uptime_secs

- **WHEN** `crews()` is called and a crew has `status == "stopped"`
- **THEN** that crew's entry does NOT include `uptime_secs` (or it is null)

#### Scenario: last_task_at populated when tasks have been dispatched

- **WHEN** `crews()` is called and at least one task has been dispatched to a crew
- **THEN** that crew's `last_task_at` is an ISO 8601 timestamp reflecting when the most recent task was dispatched

#### Scenario: last_task_at is null for crews with no task history

- **WHEN** `crews()` is called and a crew has never had a task dispatched
- **THEN** that crew's `last_task_at` is null
