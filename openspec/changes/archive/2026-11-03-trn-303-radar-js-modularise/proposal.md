# Proposal

## Why

`radar/static/app.js` is a single ~350-line file with a monolithic `renderCrews()` function. TRN-300 and TRN-301 add 11 features (gateway health, uptime, copy-to-clipboard, captain staleness warnings, host capacity bar, etc.) — landing them all in one file will make it unreadable and hard to test piecemeal. The refactor creates a clean base before feature additions.

## What Changes

- Split `radar/static/app.js` into focused modules:
  - `format.js` — date/uptime/duration helpers (`fmtDate`, `fmtUptime`, `fmtMem`)
  - `state.js` — mutable UI state (`openDetails` set, `paused` flag, last successful fetch timestamp)
  - `render.js` — DOM construction (`renderTable`, `renderRow`, `renderDetail`)
  - `data.js` — fetch/poll loop (`fetchFleet`, `startPolling`, `stopPolling`)
  - `main.js` — wiring and init (`DOMContentLoaded` listener, event delegation)
- Static files served as plain ES modules via `<script type="module">` in `index.html`
- No build step, no bundler, no new dependencies
- All existing behaviour preserved — no visual changes, no API changes
- `app.js` removed once modules are in place

No spec-level behavior changes — this is a pure internal restructuring of the Radar SPA frontend.

## Capabilities

### New Capabilities
_(none — pure refactor)_

### Modified Capabilities
_(none — no requirement changes; `ga-radar` spec requirements unchanged)_

## Impact

- `radar/static/app.js` — replaced by five modules
- `radar/static/index.html` — update script tag from `<script src="app.js">` to `<script type="module" src="main.js">`
- No changes to `radar/static/style.css`, `radar/app.py`, `radar/Containerfile`, compose, or Caddy config
- Browser support: ES modules are supported in all modern browsers; no IE11 concern given the Radar use case
