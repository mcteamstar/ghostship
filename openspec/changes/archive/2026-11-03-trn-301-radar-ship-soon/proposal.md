# Proposal

## Why

Five features that require a small amount of new logic but deliver meaningful payoff: ambient capacity awareness, early warning for stalled captains, friction reduction for MCP users, and better behaviour during investigation. All build cleanly on the module structure from TRN-303.

## What Changes

All changes are in `radar/static/`. No changes to `radar/app.py`, `radar/Containerfile`, Caddy config, or any backend.

- **`render.js` `renderTable()`** — add a capacity bar above the fleet table using `data.active_crews`, `data.max_active_crews`, `data.host_memory_available_gb` (all in the poll payload)
- **`render.js` `buildRow()` + `renderDetail()`** — captain staleness: if `cap.last_checkin_at` is older than `cap.schedule` interval × 3, show ⚠ on the captain badge and a warning row in the detail panel; add `parseInterval(scheduleStr)` helper to `format.js`
- **`render.js` `buildRow()` + `main.js`** — copy crew_id: add a copy button next to crew_id in `buildRow()`; wire via event delegation in `main.js` using `data-copy` attribute; `navigator.clipboard.writeText()` + brief checkmark feedback
- **`state.js` + `data.js`** — auto-pause: when `openDetails.size > 0`, extend poll interval to 30s; restore to 5s when all rows close. No UI toggle needed — interval adjustment is transparent
- **`state.js` + `main.js` + `render.js`** — search/filter: add `lastData` to `state.js`; cache payload in `data.js` after each fetch; render a filter `<input>` above the table only when `crews.length > 8`; `renderTable()` accepts optional filter string

## Capabilities

### New Capabilities
_(none — additions to existing Radar SPA frontend)_

### Modified Capabilities
_(none — no spec-level requirement changes)_

## Impact

- `radar/static/render.js` — `renderTable()`, `buildRow()`, `renderDetail()`
- `radar/static/format.js` — new `parseInterval()` helper
- `radar/static/state.js` — add `lastData`, `paused`/interval logic
- `radar/static/data.js` — cache `lastData`, adjust poll interval based on `openDetails`
- `radar/static/main.js` — event delegation for copy button, filter input rendering
- `radar/static/index.html` — filter input element (or rendered dynamically)
