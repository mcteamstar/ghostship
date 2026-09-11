## Why

Ghostship's `dispatch()` always calls `/api/spawn` with no `parent_session`, so dispatched tasks are invisible in the KiroCrew dashboard — no running card, no transcript, no completion record a human can inspect without going through `pickup()`. Adding configurable dispatch modes lets operators opt in to dashboard visibility with no regression risk.

## What Changes

- Add a `mode` parameter to `dispatch()`: `"headless"` (default), `"anchored"`, or `"free"`
- `none` — current behaviour, no `parent_session` on `/api/spawn`. Zero regression.
- `shared` — every task dispatched to a crew attaches to a single shared dashboard slot (`dashboard:<crew-id>`). One tab to watch; concurrent completions serialise into one transcript.
- `unique` — each task gets its own named slot (`dashboard:<crew-id>-<task-id>`). Isolated transcripts, more slots.
- When a crew was launched with `dashboard=True`, default `mode` to `"anchored"`; otherwise default to `"headless"`.
- Expose `mode` in the `dispatch()` MCP tool docstring and in the response (echo back the effective mode).
- Store the resolved `mode` default in the crew registry at launch time so dispatch can read it without re-inspecting the launch flag.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-orchestration`: `dispatch()` gains a `mode` parameter that controls whether and how dispatched tasks attach to a KiroCrew dashboard session via `parent_session` on `/api/spawn`.

## Impact

- `transport/server.py` — `dispatch()` and `_dispatch_batch()`: add `mode` param, resolve effective mode, inject `parent_session` into spawn body when non-`none`.
- `transport/lifecycle.py` — store `mode_default` in the crew registry entry at launch (derived from the `dashboard` flag).
- No changes to `/api/spawn` contract — `parent_session` is an existing accepted field.
- Captain/Raven cron sessions use `/api/crons` and are unaffected.
- No breaking changes to existing callers — default is `none`.
