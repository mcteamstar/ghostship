## Why

When `pickup(timeout_secs=N)` holds its HTTP connection open for the full poll window, MCP clients with a shorter read timeout close the connection and surface a transport error. The caller cannot distinguish a clean timeout expiry ("task still running, keep polling") from a genuine failure — they see an identical error in both cases.

## What Changes

- `pickup` (and `_pickup_list`) SHALL cap the internal poll window at a safe maximum (`GA_PICKUP_MAX_POLL_SECS`, default 30s) so the HTTP connection is never held longer than MCP clients tolerate
- When the internal cap fires before the caller's `timeout_secs` elapses, `pickup` returns the current task state with `"reason": "timeout"` — a normal (non-error) JSON response the caller can detect and re-poll from
- The `GA_PICKUP_MAX_POLL_SECS` env var is added to `docs/configuration.md`
- Existing behaviour is preserved: `timeout_secs=0` still returns immediately; task-done and `reason="admiral_mail"` early-returns are unchanged

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-orchestration`: The "Timeout elapses before the task finishes" scenario is tightened — the response MUST NOT raise a transport error; it MUST be a normal JSON object with `"reason": "timeout"`. Add a scenario for the MCP-safe internal cap.

## Impact

- `transport/server.py` — `_pickup_single` and `_pickup_list` polling loops
- `docs/configuration.md` — `GA_PICKUP_MAX_POLL_SECS`
- No breaking change to callers — return shape is unchanged, `reason` field is additive
