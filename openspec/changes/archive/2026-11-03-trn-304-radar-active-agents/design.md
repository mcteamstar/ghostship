# Design

## Context

`_build_internal_fleet_payload()` has a documented invariant: `agents: []` always, no gateway calls. This is correct for the poll path — querying N crew gateways on every 5s tick would be O(N) latency added to the poll. The invariant must not be broken.

The solution is a separate on-demand endpoint. Radar fetches it only when a row is expanded, not on every poll tick.

## Goals / Non-Goals

**Goals:** live task list visible in the detail panel when a row is expanded; poll path unchanged.

**Non-Goals:** embedding agents in the main poll payload, WebSocket streaming, showing `last_tool` or full task output.

## Decisions

### D1 — On-demand endpoint, not poll-embedded

`GET /internal/crews/{crew_id}/agents` — new transport route, protected by `X-Transport-Token`. Calls the crew's gateway at `GET /api/tasks` (the same endpoint `pickup` uses), returns `{"agents": [...]}`. Only called when the user expands a row.

### D2 — `/api/tasks` response shape

The KiroCrew gateway `/api/tasks` returns `{"tasks": [...]}` where each task has `task_id`, `agent`, `done`, `elapsed_secs`, `last_tool`. The transport handler maps this to `{"agents": [...]}` matching the existing shape `render.js` already expects.

### D3 — Timeout and error handling

The gateway call uses a 5s timeout. If the crew is stopped or the gateway is unreachable, return `{"agents": []}` with HTTP 200 — same as the poll value. No error surfaced to Radar; the detail panel just shows "No active tasks."

### D4 — Radar fetch path

`render.js` already has `loadCrons(crewId, container)` called on row expand. Add a parallel `loadAgents(crewId, container)` call alongside it. `loadAgents` fetches `/api/crews/{crewId}/agents`, then calls `renderAgents(agents)` and injects the result into the detail panel, replacing the "No active tasks." placeholder. On error or empty: no-op.

### D5 — No caching

The on-demand fetch is triggered by row expand — user-initiated, not on a timer. No cache needed. If the user leaves the row open and wants a refresh, they collapse and re-expand.

## Risks / Trade-offs

A crew with many tasks could be slow to expand if its gateway is under load. 5s timeout is the safety valve. The existing "No active tasks." fallback is shown while loading.

## Migration Plan

Additive. New routes only; no changes to existing poll behaviour.
