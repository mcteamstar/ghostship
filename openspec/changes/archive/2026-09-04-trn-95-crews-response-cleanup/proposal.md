## Why

The `crews()` MCP tool returns per-agent entries that include `last_tool` — a raw tool invocation string (e.g. `"Reading SKILL.md:1"`) fetched live from the crew gateway. While technically current, it carries no useful context at the fleet overview level and requires a `pickup` call to interpret. `pickup` and `captain status` provide live, contextual detail cheaply; `crews` should be a fast fleet overview, not a raw activity dump.

## What Changes

- **Remove `last_tool`** from each agent entry in the `crews()` response — a live but low-signal raw tool string that requires `pickup` to interpret.
- **Keep `task_id`, `agent`, `done`, `elapsed_secs`** in each agent entry — `elapsed_secs` is computed live from task start time and remains useful.
- **Add `last_task_at`** to each crew object — ISO 8601 timestamp of when the last task was dispatched to the crew. Already stored in the registry; surfaced consistently on every crew object.
- **Add `uptime_secs`** to each crew object — seconds since the container started, from Podman inspect `StartedAt`. Only present when `status == "running"`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-server`: The `crews()` response schema changes — `last_tool` removed from agent entries; `last_task_at` and `uptime_secs` added to crew objects.

## Impact

- `transport/server.py` (or `transport/lifecycle.py`) — `_crews()` handler response construction.
- MCP tool docstring for `crews` — update to reflect new fields and removal of `last_tool`.
- `ghostship-command` skill — update guidance on how to use `crews` vs `pickup`.
- Tests — update assertions on `crews()` response shape.
