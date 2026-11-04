# Design

## Context

See proposal.md — Why. The current `radar/static/app.js` is a 342-line IIFE with all concerns mixed together. The module split targets the feature additions in TRN-300/301 that follow.

The existing file uses an IIFE (`(function(){})()`) with `"use strict"` for encapsulation, which was appropriate when there were no modules. ES modules provide the same encapsulation (`import`/`export` are scoped by default) without the wrapper.

## Goals / Non-Goals

**Goals:**
- Split by concern so each TRN-300/301 feature touches one file
- No build step, no bundler, no new runtime dependencies
- Identical user-visible behaviour

**Non-Goals:**
- Unit testing (no test runner for frontend JS today — out of scope)
- TypeScript conversion
- Any feature work (TRN-300/301 land after this)
- IE11 / legacy browser support

## Decisions

### D1 — ES modules via `<script type="module">` (no bundler)

`index.html` already serves static files baked into the container. Switching the script tag to `<script type="module" src="main.js">` and using `import`/`export` across the five files requires no build step and no changes to `radar/app.py`, `radar/Containerfile`, or Caddy config.

**Alternative considered:** single-file concatenation via a Makefile step. Rejected — adds a build dependency to the image, complicates the Containerfile, and saves nothing at this scale.

**Alternative considered:** a bundler (esbuild/vite). Rejected — adds `node_modules`, a build step, and npm to the image. No framework warrants it.

### D2 — Five-module split

```
radar/static/
├── format.js   # Pure helpers: fmtUptime, fmtDate, statusBadge, esc
├── state.js    # Mutable singletons: openDetails Set, lastFetchOk timestamp
├── render.js   # DOM builders: renderTable, buildRow, renderDetail, renderAgents, loadCrons
├── data.js     # Fetch/poll: fetchFleet, startPolling, stopPolling
└── main.js     # Wiring: DOMContentLoaded, event delegation, kick-off
```

`app.js` is deleted after the split is verified.

**Ownership by module for TRN-300/301 features:**
- gateway health badge → `render.js`
- uptime column → `render.js` + `format.js`
- image version in detail → `render.js`
- timestamp tooltips → `format.js`
- page title → `main.js` (one-liner in render callback)
- error/staleness UI → `state.js` (track `lastFetchOk`) + `main.js` (update DOM)
- host capacity bar → `render.js` + `data.js` (pass top-level fields)
- captain staleness → `render.js` + `format.js`
- copy crew_id → `render.js` (button HTML) + `main.js` (event delegation)
- auto-pause → `state.js` + `data.js`
- search filter → `main.js` + `render.js`

### D3 — `state.js` exports mutable singletons

`openDetails` (Set) and `lastFetchOk` (Date|null) are shared across `render.js` and `data.js`. Exporting them as named mutable exports from `state.js` keeps the coupling explicit and avoids threading them as function arguments through every call.

```js
// state.js
export const openDetails = new Set();
export let lastFetchOk = null;
export function markFetchOk() { lastFetchOk = new Date(); }
```

## Risks / Trade-offs

**ES module `import` requires same-origin or CORS** → Not an issue; all five files are served from the same `ga-radar` origin on `/static/*`.

**`<script type="module">` defers by default** → The current `app.js` is loaded at the bottom of `<body>`, so execution order is already after DOM parse. Module defer is equivalent here; no change needed.

**`fetch` with `credentials: "include"` already in `data.js`** → No change; session cookie behaviour is unchanged.

## Migration Plan

1. Create the five new files alongside `app.js`
2. Update `index.html` to `<script type="module" src="main.js">`
3. Smoke test: open Radar in a browser, verify table renders, rows expand, polling works
4. Delete `app.js`
5. Ship as a standalone PR — TRN-300/301 branch off main after this merges

Rollback: revert the `index.html` change and restore `app.js` from git. One-line revert.

## Open Questions

None. All decisions are resolvable from the current codebase.
