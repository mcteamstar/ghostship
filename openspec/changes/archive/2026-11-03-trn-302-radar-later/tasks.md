# Tasks

`state.lastData` and `setLastData()` are already present from TRN-301 — no prerequisite work needed.

## 1. URL fragment deep-linking

- [x] 1.1 In `main.js`, after the first `fetchFleet()` resolves, parse `window.location.hash`: if it matches `#crew=<id>`, add `<id>` to `openDetails` (from `state.js`), then call `renderTable(state.lastData)` to open the row
- [x] 1.2 In `render.js` row-click handler: on row open, call `history.replaceState(null, "", "#crew=" + crewId)`; on row close, call `history.replaceState(null, "", location.pathname)`

## 2. Column sort by last_task_at

- [x] 2.1 Add `export let sortDir = null; export function toggleSortDir() { sortDir = sortDir === null ? "desc" : sortDir === "desc" ? "asc" : null; }` to `state.js`
- [x] 2.2 In `render.js` `renderTable()`, if `state.sortDir` is not null, sort the `running` and `stopped` arrays by `last_task_at` (nulls to end) before building rows
- [x] 2.3 In `render.js`, add a click handler to the "Last Task" `<th>` that calls `state.toggleSortDir()` and calls `renderTable(state.lastData)` to re-render
- [x] 2.4 In `index.html`, add `class="sortable"` and `style="cursor:pointer"` to the "Last Task" `<th>`; update the header text in `renderTable()` to append ` ▲` or ` ▼` based on `state.sortDir`

## 3. Verify and commit

- [x] 3.1 Smoke test: verify hash deep-link opens correct row on load, sort toggles correctly within groups
- [x] 3.2 Commit on `release/0.11.1`
