# Proposal

## Why

The captain monitor stalls after every Raven check-in completes. Root cause confirmed by Wraith investigation on carrier (task `b87079e565bc33d2`): `_steer_captain_checkin` tries to `/continue` a completed Raven session, the gateway returns `400 Bad Request` (session gone), but `_crew_api_with_recovery` misroutes 400 to the stale-cookie recovery path, exhausts its retries, raises `CrewUnresponsiveError`, and the catch block in `_steer_captain_checkin` doesn't recognise this as a "session gone" case — it re-raises instead of falling back to `_dispatch_captain_checkin`. The schedule advances but `current_task_id` is never cleared, so every subsequent tick repeats identically. The bug is latent since v0.6.0 — no diff in the affected functions between v0.6.0 and release/0.7.0.

## What Changes

- `transport/lifecycle.py` (`_crew_api_with_recovery`): re-raise `httpx.HTTPStatusError` immediately when `status == 400` and path contains `/continue` — don't route this to phase-1 stale-cookie recovery, since a finished session can't be fixed by refreshing the cookie.
- `transport/server.py` (`_steer_captain_checkin`): add `"400 Bad Request" in err_str` to the conversation-gone fallback condition, and clear `current_task_id` from the registry before calling `_dispatch_captain_checkin` so a subsequent tick doesn't retry the dead task.
- Unit test covering the 400-on-/continue path.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `autonomous-orchestration`: the captain check-in monitor SHALL recover from a 400 response on `/continue` by falling back to a fresh dispatch, same as it already does for 404.

## Impact

- `transport/lifecycle.py` — `_crew_api_with_recovery`, ~3 lines
- `transport/server.py` — `_steer_captain_checkin`, ~5 lines + registry clear
- `tests/unit/test_captain.py` or `test_monitors.py` — new test
