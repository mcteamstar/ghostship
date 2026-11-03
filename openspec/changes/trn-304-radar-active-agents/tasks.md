# Tasks

## 1. Transport — new per-crew agents endpoint

- [ ] 1.1 In `transport/tools.py`, add `_get_crew_agents(info: dict) -> list` — queries `GET {crew_url}/api/tasks` with a 5s timeout; returns the `tasks` array mapped to `{"task_id", "agent", "done", "elapsed_secs"}` dicts; returns `[]` on any error or non-200
- [ ] 1.2 In `transport/server.py`, add route `GET /internal/crews/{crew_id}/agents` (`_handle_internal_crew_agents_get`): look up crew by `crew_id` in registry; if not found return 404; if not running return `{"agents": []}`; otherwise call `_get_crew_agents(info)` and return `{"agents": [...]}`
- [ ] 1.3 Add the new route to `_TRANSPORT_SECRET_ONLY_ROUTES` (portside-internal, `X-Transport-Token` required)
- [ ] 1.4 Add unit test in `tests/unit/test_radar_server.py` or a new file: mock the crew gateway, assert the endpoint returns the mapped task list; assert stopped crew returns `{"agents": []}`

## 2. Radar server — proxy route

- [ ] 2.1 In `radar/server.py`, add route `GET /api/crews/{crew_id}/agents` (`api_crew_agents`): proxy to `GET {TRANSPORT_URL}/internal/crews/{crew_id}/agents` with `X-Transport-Token`; return 502 on transport error; pass through response on success
- [ ] 2.2 Add unit test asserting the proxy forwards correctly and handles 502

## 3. Radar frontend — load agents on row expand

- [ ] 3.1 In `radar/static/render.js` `renderTable()` row-click handler, add a parallel `loadAgents(crewId, detailTr.querySelector(".detail-inner"))` call alongside the existing `loadCrons()` call (only for running crews)
- [ ] 3.2 Add `export function loadAgents(crewId, container)` to `render.js`: fetch `/api/crews/{encodeURIComponent(crewId)}/agents`; on success call `renderAgents(data.agents)` and prepend the result into `container` (before the captain section); on error or empty agents: no-op (existing "No active tasks." placeholder remains)

## 4. Verify and commit

- [ ] 4.1 Smoke test: open Radar on a crew with active tasks, expand the row, verify agents appear
- [ ] 4.2 Smoke test: expand a stopped crew row, verify "No active tasks." shown, no errors
- [ ] 4.3 Commit on `release/0.11.1`
