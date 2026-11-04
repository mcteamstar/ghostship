# Tasks

## 1. Host capacity bar

- [x] 1.1 In `render.js` `renderTable()`, before building the row HTML, prepend a `<tr class="capacity-row"><td colspan="7">` showing `data.active_crews + " / " + data.max_active_crews + " crews · " + data.host_memory_available_gb.toFixed(1) + " GB free"` with a simple `<progress>` bar
- [x] 1.2 Add `.capacity-row` styles to `style.css`

## 2. Captain staleness warning

- [x] 2.1 Add `parseInterval(scheduleStr)` to `format.js` — parses `"every Ns"` → milliseconds; returns `null` for unrecognised formats
- [x] 2.2 In `render.js` `buildRow()`, if captain is enabled and `cap.last_checkin_at` is set, compute staleness via `parseInterval(cap.schedule)` — if elapsed > interval × 3, replace the `⚑ captain` badge with `⚑ captain ⚠`
- [x] 2.3 In `render.js` `renderDetail()`, add a warning row to the captain table when staleness is detected: `"No check-in for Xm — captain may be stalled"`

## 3. Copy crew_id to clipboard

- [x] 3.1 In `render.js` `buildRow()`, add `<button class="copy-btn" data-copy="<crew_id>" title="Copy crew ID">⧉</button>` after the crew_id text in the first cell
- [x] 3.2 In `main.js`, add a delegated `click` listener on `bodyEl` for `[data-copy]` buttons: call `navigator.clipboard.writeText(btn.dataset.copy)`, then temporarily set `btn.textContent = "✓"` for 1.5s
- [x] 3.3 Add `.copy-btn` styles (minimal: no border, cursor pointer) to `style.css`

## 4. Auto-pause when rows open

- [x] 4.1 In `data.js` `fetchFleet()`, add an early-return guard at the top: `if (openDetails.size > 0 && state.lastFetchOk && Date.now() - state.lastFetchOk < 25000) return;`

## 5. Search / filter bar

- [x] 5.1 Add `export let lastData = null; export function setLastData(d) { lastData = d; }` to `state.js`
- [x] 5.2 In `data.js` `fetchFleet()` success handler, call `state.setLastData(data)` before `renderTable(data)`
- [x] 5.3 In `render.js` `renderTable(data, filter)`, accept optional second arg; if `filter` is set, filter `crews` by `crew.crew_id.toLowerCase().includes(filter) || (crew.composition || "").toLowerCase().includes(filter)` before partitioning into running/stopped
- [x] 5.4 In `main.js`, after `fetchFleet()` resolves: if `state.lastData.crews.length > 8`, inject a `<input id="fleet-filter" placeholder="Filter crews…">` above the table; add `input` listener that calls `renderTable(state.lastData, e.target.value.toLowerCase())`
- [x] 5.5 Add `#fleet-filter` styles to `style.css`

## 6. Verify and commit

- [x] 6.1 Smoke test: open Radar, verify all five features, no regressions
- [x] 6.2 Commit on `release/0.11.1`
