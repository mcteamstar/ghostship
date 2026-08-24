## Context

`pickup(timeout_secs=N)` holds its HTTP connection open while polling in a `while True` loop with `time.sleep(3)` between iterations. MCP clients enforce their own read timeout independently of what the transport is doing. When the MCP client's read timeout fires before the poll loop exits naturally, the client closes the connection and reports a transport error — indistinguishable from a genuine failure.

The polling loop in `_pickup_single` (and `_pickup_list`) already exits cleanly when `remaining <= 0`, returning the current state without raising. The problem is that `remaining` may never reach 0 within the MCP client's patience window.

## Approach

Introduce `GA_PICKUP_MAX_POLL_SECS` (default 30s) as an internal server-side cap. The effective poll deadline becomes:

```
effective_deadline = now + min(timeout_secs, GA_PICKUP_MAX_POLL_SECS)
```

When that deadline fires, the loop exits and returns `{"reason": "timeout", ...}` — a normal JSON response, not an exception. The caller sees a non-error result, reads `"done": false, "reason": "timeout"`, and knows to re-poll.

The default of 30s is conservative — most MCP clients allow at least 60s, but 30s leaves comfortable headroom while still allowing useful polling intervals of up to ~10 iterations of 3s each.

## Key Decisions

**Why a server-side cap rather than a client-side fix?**
The server controls the HTTP connection lifetime. Client-side workarounds (shorter `timeout_secs`) are fragile and shift the burden to every caller. A server-side cap is a single change that fixes all callers.

**Why add `reason: "timeout"` to the response?**
Without it, a caller receiving `done: false` with no `reason` field cannot tell whether the poll cap fired (re-poll expected) or the task hit its own timeout (no point re-polling). The `reason` field is additive and consistent with the existing `reason: "admiral_mail"` early-return pattern.

**`_pickup_list` gets the same cap**
The list-all variant has the same structure and the same exposure. Cap both with a single helper or by passing `effective_timeout = min(timeout_secs, GA_PICKUP_MAX_POLL_SECS)` down to both.

## Implementation

In `server.py`:

1. Read `GA_PICKUP_MAX_POLL_SECS = int(os.environ.get("GA_PICKUP_MAX_POLL_SECS", "30"))` at module level alongside other `GA_*` vars.
2. In the `pickup` tool function, clamp `effective_timeout`:
   ```python
   effective_timeout = min(max(0, timeout_secs), GA_PICKUP_MAX_POLL_SECS) if timeout_secs > 0 else 0
   ```
3. In `_pickup_single` and `_pickup_list`, add `"reason": "timeout"` to the `out` dict before returning when `remaining <= 0` and `done` is False.
4. Add `GA_PICKUP_MAX_POLL_SECS` to `docs/configuration.md`.

No schema changes, no dependency changes.
