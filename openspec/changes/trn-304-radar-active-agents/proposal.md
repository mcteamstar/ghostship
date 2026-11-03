# Proposal

## Why

`/internal/crews` (the transport endpoint `ga-radar` proxies) intentionally returns `agents: []` for all crews — by design, to avoid hammering per-crew gateways at 5-second poll intervals. This means Radar never shows active tasks, the agent count badge in TRN-301 can never render, and `renderDetail()` always says "No active tasks." even when two Ghosts are mid-implementation.

The fix is to make agent data available on-demand (not on every poll) — either via a separate endpoint Radar calls only when a row is expanded, or by adding a lightweight cached layer in transport.

## What Changes

- **`transport/tools.py` `_build_internal_fleet_payload()`** — no change to the main polling path; `agents: []` stays for the 5-second poll
- **New route `GET /internal/crews/{crew_id}/agents`** in `transport/server.py` — returns live agent/task list for one crew by querying its gateway; only called when Radar expands a row
- **`radar/server.py`** — add `GET /api/crews/{crew_id}/agents` route that proxies the new transport endpoint
- **`radar/static/render.js` `loadCrons()`** — already called on row expand; extend it (or add a parallel `loadAgents()` call) to fetch `/api/crews/{crew_id}/agents` and inject live task data into the detail panel
- **`openspec/specs/ga-radar/spec.md`** — add the new route to the route table and scenario

## Capabilities

### New Capabilities
- `ga-radar/active-agents` — live per-crew agent list available on row expand

### Modified Capabilities
- `ga-radar` — new route added; existing poll behaviour unchanged

## Impact

- `transport/server.py` — new `/internal/crews/{crew_id}/agents` route
- `transport/tools.py` — new `_get_crew_agents()` helper (queries crew gateway `/api/tasks`)
- `radar/server.py` — new `/api/crews/{crew_id}/agents` proxy route
- `radar/static/render.js` — `loadAgents()` called on row expand alongside `loadCrons()`
- `openspec/specs/ga-radar/spec.md` — delta spec
