# Design

## Context

See proposal.md — Why. All five features are frontend-only additions to the TRN-303 module structure. The most interesting design question is auto-pause (how to adjust the poll interval without a visible toggle) and copy-to-clipboard (how to avoid re-registering event listeners on every render).

## Goals / Non-Goals

**Goals:** five features, each isolated to its owning module, no backend changes, no new dependencies.

**Non-Goals:** write operations (nuke, dispatch, stop) from Radar, SSE, new API routes.

## Decisions

### D1 — Auto-pause via interval adjustment, not a flag

Rather than a `paused` boolean that skips fetches entirely, `data.js` checks `openDetails.size` at the start of each poll cycle and uses a 30s interval when rows are open, 5s when all are closed. Implemented by clearing and resetting `setInterval` in a wrapper, or by checking elapsed time since last fetch inside the existing interval. The simpler approach: keep one interval at 5s but add an early-return guard: `if (openDetails.size > 0 && Date.now() - lastFetchOk < 25000) return;`. No UI change.

### D2 — Copy button via event delegation

`buildRow()` renders `<button class="copy-btn" data-copy="<crew_id>" title="Copy crew ID">⧉</button>`. A single delegated listener on `bodyEl` in `main.js` handles all `.copy-btn` clicks — no per-row listener registration, no re-wiring on re-render. Feedback: swap button text to `✓` for 1.5s via `setTimeout`.

### D3 — `lastData` cached in `state.js`

`data.js` calls `state.setLastData(data)` after each successful fetch. `main.js` filter input calls `renderTable(state.lastData, filterText)` on `input` event. `renderTable()` accepts an optional second argument `filter` — if set, crew list is filtered before building rows.

### D4 — Capacity bar placement

A `<div class="capacity-bar">` injected before `<tbody>` — or more simply, a new `<tr class="capacity-row">` as the first row inside the table (colspan=7). The latter requires no HTML structure changes and is consistent with the existing section-divider pattern.

## Risks / Trade-offs

**Auto-pause early-return**: if `lastFetchOk` is null (first load), the guard is skipped — correct behaviour. If the transport goes down while a row is open, the 25s guard means the error state takes up to 25s to surface. Acceptable given the row-is-open context.

**Search filter re-render**: calling `renderTable(lastData, filter)` on every keypress re-renders the full table. At typical fleet sizes (<20 crews) this is imperceptible.

## Migration Plan

All additive. Revert commit to rollback.
