# TRN-205 — `POST /logout` aborts a pending login flow

**Plane ticket:** TRN-205
**Change:** `trn-205-logout-abort-pending-login`

## Problem

`POST /logout` clears `ga-kiro-auth` but does not cancel an in-progress login flow.
The login container keeps running and `_login_pending` stays set, making it impossible
to start a fresh login without restarting the transport. The only recovery today is a
service restart — as experienced during the 0.6.0 e2e test run where the auth cycle
test left the transport stuck for ~15 minutes.

The same issue exists for Claude (`_claude_login_pending`) and Codex
(`_codex_login_pending`) — logout clears the credential file but not the pending state.

## Solution

`POST /logout` (and `/logout/claude`, `/logout/codex`) should:
1. Clear the credential file (existing behaviour)
2. Kill the in-progress login container if one is running
3. Clear the `_*_login_pending` state so a fresh `POST /login` can be issued immediately

This makes logout idempotent from the operator's perspective: after `POST /logout`,
the transport is always in a clean unauthenticated state regardless of what was
in-flight.

## What changes

### `lifecycle.py`

- `_abort_pending_login()` — acquires `_login_pending_lock`, nukes the login container
  if `_login_pending["container"]` is set, sets `_login_pending = None`
- `_abort_claude_pending_login()` — same for `_claude_login_pending`
- `_abort_codex_pending_login()` — same for `_codex_login_pending`

### `server.py`

- `_handle_logout_post` — call `_abort_pending_login()` after clearing `ga-kiro-auth`,
  regardless of whether a flow was pending (no-op if not)
- `_handle_claude_logout_post` — call `_abort_claude_pending_login()`
- `_handle_codex_logout_post` — call `_abort_codex_pending_login()`

### Response change

When logout aborts an in-progress flow, include `"aborted_pending_login": true` in
the response body so the caller knows a flow was killed. No change to HTTP status code.

## Non-goals

- A separate `DELETE /login` or `POST /login/abort` endpoint — logout is the right
  surface for this, no new routes needed
- Exposing the pending state directly via `GET /login` — it already returns
  `{"status": "pending"}` which is sufficient

## Affected files

| File | Change |
|:-----|:-------|
| `transport/lifecycle.py` | `_abort_pending_login()`, `_abort_claude_pending_login()`, `_abort_codex_pending_login()` |
| `transport/server.py` | Three logout handlers updated to call abort helpers |
| `tests/unit/test_auth.py` | Tests for abort-on-logout behaviour |
