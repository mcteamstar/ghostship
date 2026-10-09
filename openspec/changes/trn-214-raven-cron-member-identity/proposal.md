# TRN-214: Raven cron session lacks member identity on 0.8.0

The entire Captain workflow (sdd, indy, free-form orders) is broken on KiroCrew 0.8.0.
Raven dispatched via a cron job gets `member_identity_unavailable` (HTTP 409) when it
attempts `POST /api/spawn`, even when sending both `X-Internal-Secret` and
`X-Session-Key: $KIRO_SESSION_ID`.

See Plane ticket TRN-214 for full root cause analysis, timeline, and approach options.

## Approaches to investigate (in order)

1. Pass `parent_session: "dashboard:member-raven"` in `POST /api/crons` body
   (`server.py:_captain_do_order ~line 3020`) — verify KiroCrew 0.8.0 cron API
   accepts and threads it through to each fired spawn.

2. Use `dispatch()` + `schedule(delay=interval)` instead of a cron — fire Raven
   via transport's own member-slot dispatch, have Raven reschedule itself.

3. Check KiroCrew 0.8.0 vs insider.8 diff for what changed in cron/attestation
   (`messaging.py:587` — `"cron:"` prefix in parent_session check).
