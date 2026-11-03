# Tasks

## 1. Gateway health indicator

- [x] 1.1 In `render.js` `buildRow()`, modify `statusBadge()` call: if `crew.gateway_healthy === false`, append ` <span class="badge badge-warn" title="Gateway unreachable">⚠</span>` after the status badge
- [x] 1.2 Add `.badge-warn` style to `style.css`

## 2. Uptime column

- [x] 2.1 In `render.js` `buildRow()`, change `fmtDate(crew.created_at)` to `crew.status === "running" ? fmtUptime(crew.uptime_secs) : fmtDate(crew.created_at)`
- [x] 2.2 In `index.html`, rename the "Age" column header `<th>` to "Uptime"
- [x] 2.3 Update `docs/radar.md` to fix any "Age" column reference

## 3. Crew image version in detail

- [x] 3.1 In `render.js` `renderDetail()`, add a line showing `crew.crew_image_version` (if present) near the top of the detail panel

## 4. Absolute timestamp tooltip

- [x] 4.1 In `format.js` `fmtDate()`, wrap the return value: `return "<span title=\"" + esc(iso) + "\">" + relative + "</span>"` — apply to all return paths that produce a relative string (not the `"—"` fallback)

## 5. Page title crew count

- [x] 5.1 In `data.js` `fetchFleet()` success handler, after `renderTable(data)`, add: `document.title = "Fleet Radar (" + (data.crews || []).filter(c => c.status === "running").length + " running)";`

## 6. Error and staleness UI

- [x] 6.1 In `data.js` `fetchFleet()` error handler, improve error message: distinguish `TypeError` (network error) from HTTP errors (transport unreachable) with specific copy per design.md D3
- [x] 6.2 In `data.js`, after `renderTable(data)` in the success handler, add a staleness check: if `state.lastFetchOk` is set and `Date.now() - state.lastFetchOk > 30000`, add class `stale-critical` to `statusEl`; if `> 15000`, add `stale`; else remove both
- [x] 6.3 Add `.stale` (amber text) and `.stale-critical` (red text) rules to `style.css`

## 7. Verify and commit

- [x] 7.1 Open Radar in browser — verify all six features visible, no regressions
- [x] 7.2 Commit on `release/0.11.1`
