# Tasks

## 1. Create format.js

- [x] 1.1 Create `radar/static/format.js` exporting `fmtUptime`, `fmtDate`, `statusBadge`, `esc` — extracted verbatim from `app.js` helpers section

## 2. Create state.js

- [x] 2.1 Create `radar/static/state.js` exporting `openDetails` (Set), `lastFetchOk` (let, null), and `markFetchOk()` function

## 3. Create render.js

- [x] 3.1 Create `radar/static/render.js` importing from `format.js` and `state.js`; export `renderTable`, `buildRow`, `renderDetail`, `renderAgents`, `loadCrons`
- [x] 3.2 Verify `openDetails` is read from `state.js` (not a local variable)

## 4. Create data.js

- [x] 4.1 Create `radar/static/data.js` importing from `render.js` and `state.js`; export `fetchFleet` and `startPolling`
- [x] 4.2 `fetchFleet` calls `markFetchOk()` on success; sets `state.lastFetchOk = null` on error (for TRN-300 staleness UI hook)

## 5. Create main.js and update index.html

- [x] 5.1 Create `radar/static/main.js` importing from `data.js`; wire `DOMContentLoaded`, kick off initial fetch and polling interval
- [x] 5.2 Update `radar/static/index.html`: change `<script src="app.js">` to `<script type="module" src="main.js">`

## 6. Smoke test and cleanup

- [x] 6.1 Open Radar in a browser — verify fleet table renders, rows are expandable, polling updates the "Refreshed at" timestamp
- [x] 6.2 Delete `radar/static/app.js`
- [x] 6.3 Confirm `openspec validate trn-303-radar-js-modularise` passes
- [ ] 6.4 Commit on `release/0.11.1`
