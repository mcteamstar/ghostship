# Proposal

## Why

Two conditional improvements for when Radar is shared across people or the fleet grows larger. Neither is urgent at the current scale but both are clean additions to the modular structure from TRN-303.

## What Changes

All changes are in `radar/static/`. No backend changes.

- **`main.js` + `render.js` + `state.js`** — URL fragment deep-linking: on first load, parse `window.location.hash` (format: `#crew=<id>`) and pre-open the matching row by seeding `openDetails`; in the row-click handler, call `history.replaceState()` to update the hash on open/close. The hash only needs seeding once — `openDetails` already persists across re-renders.
- **`state.js` + `render.js`** — column sort by `last_task_at`: add `sortField`/`sortDir` to `state.js`; add a click handler to the "Last Task" `<th>` that toggles direction and triggers a re-render; sort within running and stopped groups separately (don't mix groups); show ▲/▼ in the header. Client-side only.

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities
_(none — no spec-level requirement changes)_

## Impact

- `radar/static/main.js` — hash parsing on load
- `radar/static/render.js` — hash update in row-click, sort logic in `renderTable()`, ▲/▼ in header, `<th>` click handler
- `radar/static/state.js` — `sortField`, `sortDir` exports
