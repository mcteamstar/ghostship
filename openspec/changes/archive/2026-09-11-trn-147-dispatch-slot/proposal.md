## Why

The `mode` parameter (`headless`/`anchored`/`free`) shipped in TRN-133 is the right idea but the wrong abstraction — it hides what's actually happening (attaching to a named dashboard slot) and locks the consuming agent into a fixed vocabulary. Replacing it with a `slot` parameter exposes the underlying mechanism directly, giving agents full flexibility to route task completions to any named session they choose.

## What Changes

- **BREAKING**: Remove `mode: str` parameter from `dispatch()` and `_dispatch_batch()`
- Add `slot: str | bool | None` parameter to `dispatch()` and `_dispatch_batch()`
- `slot=None` (default, no dashboard) — headless, no `parent_session`, task invisible in dashboard
- `slot="bridge"` (default, dashboard active) — tasks attach to the crew's shared `"bridge"` slot
- `slot=True` — auto-generate a unique slot name per task (`uuid4().hex[:8]` suffix); each task gets its own dedicated session
- `slot="<name>"` — attach to any named slot; multiple dispatches with the same name share one session
- Default resolution: `"bridge"` if crew has `dashboard_port` set, `None` otherwise
- Echo resolved slot name (or null) in dispatch response as `"slot"` field
- Pre-create the slot via `POST /api/chat/slots` before dispatching (409 = already exists, ok)
- Update `dispatch()` docstring, unit tests, and spec

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-orchestration`: `dispatch()` gains a `slot` parameter replacing `mode`; the slot parameter controls dashboard session routing with a flexible named-slot model

## Impact

- `transport/server.py` — `dispatch()`: replace `mode` with `slot`, update resolution logic and docstring
- `transport/lifecycle.py` — `_dispatch_batch()`: replace `mode` with `slot`
- `tests/unit/test_dispatch_modes.py` — rewrite for `slot` parameter
- **Breaking change** for any caller passing `mode=` explicitly (the MCP tool schema changes)
- No change to headless behaviour for callers that pass neither `mode` nor `slot`
