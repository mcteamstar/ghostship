# Design

## Context

See proposal.md — Why. Two features, both pure frontend. URL fragment deep-linking is straightforward given `openDetails` already persists across renders. Column sort is the more involved of the two.

## Goals / Non-Goals

**Goals:** deep-linkable crew rows, sortable last_task_at column — both client-side only.

**Non-Goals:** server-side sort, multi-column sort, sort persistence across page reloads.

## Decisions

### D1 — Hash format: `#crew=<id>`

Single-crew focus. Multiple open rows could be encoded as `#crew=a,b` but that adds complexity for a rare use case. Start with single. If a second row is opened while a hash is set, update the hash to the newly opened crew (most recent).

### D2 — Hash updated with `history.replaceState`, not `location.hash =`

`location.hash = x` causes a scroll-to-anchor. `history.replaceState(null, "", "#crew=" + id)` does not. On close: `history.replaceState(null, "", location.pathname)` clears it cleanly.

### D3 — Sort state in `state.js`

`export let sortDir = null; // null | "asc" | "desc"`  
`null` = default order (insertion order within groups). Toggle: `null → "desc" → "asc" → null`. `renderTable()` reads `state.sortDir` and sorts the `running` and `stopped` arrays by `last_task_at` before building rows (nulls sort to end). The `<th>` click handler updates `state.sortDir` and calls `renderTable(state.lastData)` — requires `lastData` from TRN-301, or this change depends on TRN-301.

**Dependency note:** TRN-302 sort feature depends on `state.lastData` introduced in TRN-301. Implement TRN-301 first, or implement the `lastData` cache as part of this change.

## Risks / Trade-offs

`history.replaceState` in `render.js` couples a DOM module to browser history. Acceptable — Radar is a single-page SPA; the coupling is shallow.

## Migration Plan

Additive. Revert commit to rollback.
