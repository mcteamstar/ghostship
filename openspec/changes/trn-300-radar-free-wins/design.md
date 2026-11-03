# Design

## Context

See proposal.md — Why. All six features use data already in the poll payload. The module structure from TRN-303 makes each feature a clean, isolated edit. `state.js` already exports `lastFetchOk`/`markFetchOk()`/`clearFetchOk()` which the staleness feature relies on.

## Goals / Non-Goals

**Goals:** render six hidden-but-available data points with no new fetches, no backend changes, no new dependencies.

**Non-Goals:** changing the poll interval, adding new API routes, touching auth or Caddy.

## Decisions

### D1 — `fmtDate()` returns HTML span for tooltip

`fmtDate()` currently returns a plain string. Changing it to return `<span title="ISO">relative</span>` is safe because all callers embed the result in HTML via string concatenation — they already treat the return as HTML. The `esc()` call on the ISO date in the `title` attribute handles any edge-case characters.

### D2 — Staleness thresholds: 15s / 30s

`REFRESH_INTERVAL` is 5s. A missed poll could be a hiccup; 3 missed polls (15s) is stale; 6 missed polls (30s) is critical. The check runs inside the existing `setInterval` callback — no new timer needed. `statusEl` class list: remove both classes on success, toggle them on the existing error path and on a new staleness check added after `renderTable()`.

### D3 — Error message copy

Current: `"Fetch error: " + err`. Proposed:
- `err instanceof TypeError` → `"Network error — check your connection"`
- `err.message.includes("502")` or `"503"` or `"504"` → `"Transport unreachable — check ga-transport is running"`
- Fallback: `"Fetch error: " + err.message`

## Risks / Trade-offs

`fmtDate()` returning HTML means callers must not double-escape it. All current callers use `+` string concatenation into HTML, so this is safe. If a future caller uses `textContent` assignment it would show raw HTML — that's a future concern, not a present one.

## Migration Plan

All changes are additive. No rollback strategy needed beyond reverting the commit.
