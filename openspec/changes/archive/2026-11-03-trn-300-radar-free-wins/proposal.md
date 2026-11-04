# Proposal

## Why

Six pieces of data are already in the `/api/crews` poll payload but not rendered: `gateway_healthy`, `uptime_secs`, `crew_image_version`, ISO timestamps, `active_crews`/`max_active_crews`, and `lastFetchOk` (tracked since TRN-303). These are zero-cost observability wins — no backend changes, no new API calls, pure frontend additions to the modularised Radar SPA.

## What Changes

All changes are in `radar/static/`. No changes to `radar/app.py`, `radar/Containerfile`, Caddy config, or any backend.

- **`render.js` `buildRow()`** — add ⚠ to status badge when `crew.gateway_healthy === false`
- **`render.js` `buildRow()`** — replace `fmtDate(crew.created_at)` with `fmtUptime(crew.uptime_secs)` for running crews; rename "Age" column header to "Uptime"; update `docs/radar.md` to match
- **`render.js` `renderDetail()`** — add image version row using `crew.crew_image_version`
- **`format.js` `fmtDate()`** — wrap return value in `<span title="<ISO date>">` so hover shows the absolute date
- **`data.js` `fetchFleet()`** success handler — add `document.title = "Fleet Radar (" + runningCount + " running)"` after `renderTable(data)`
- **`data.js` + `style.css`** — use `state.lastFetchOk` (already tracked since TRN-303): apply CSS class `stale` to `statusEl` when >15s since last successful fetch, `stale-critical` when >30s; improve error message copy to distinguish transport errors ("Transport unreachable") from network errors ("Network error")

## Capabilities

### New Capabilities
_(none — pure frontend additions to existing Radar SPA)_

### Modified Capabilities
_(none — no spec-level requirement changes; `ga-radar` spec requirements unchanged)_

## Impact

- `radar/static/render.js` — `buildRow()`, `renderDetail()`
- `radar/static/format.js` — `fmtDate()`
- `radar/static/data.js` — `fetchFleet()` success and error handlers
- `radar/static/style.css` — add `.stale`, `.stale-critical` rules
- `docs/radar.md` — fix "Age" → "Uptime" column reference
