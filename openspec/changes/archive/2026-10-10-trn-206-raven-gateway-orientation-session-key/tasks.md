# Tasks: TRN-206

## 1. Fix _RAVEN_GATEWAY_ORIENTATION

- [x] 1.1 In `transport/captain.py`, find `_RAVEN_GATEWAY_ORIENTATION` (~line 53)
- [x] 1.2 In the spawn auth instruction, add `, X-Session-Key: $KIRO_SESSION_ID` alongside
  the existing `X-Internal-Secret` header instruction so it reads:
  `authenticating each request with ... X-Internal-Secret header ... and X-Session-Key: $KIRO_SESSION_ID`
- [x] 1.3 Verify the SDD template still has its own explicit instruction (it should be
  redundant after this fix but harmless to keep)

## 2. Test

- [x] 2.1 Run unit tests: `bash tests/run.sh --unit`
- [ ] 2.2 Verify free-form captain order can dispatch a persona (smoke test on starport)
  - **BLOCKED**: `X-Session-Key` fix is necessary but insufficient. Live smoke test on two
    crews confirms Raven gets `member_identity_unavailable` even with both headers correct.
    Root cause: the cron job fires Raven into a headless session (no `parent_session`), so
    `$KIRO_SESSION_ID` exists but is not an attested member session key.

## 3. Root fix — wire parent_session into the captain cron job

- [ ] 3.1 In `transport/server.py:_captain_do_order` (~line 3020), add
  `"parent_session": "dashboard:member-raven"` to the `body` dict passed to `POST /api/crons`
- [ ] 3.2 Verify KiroCrew's cron API passes `parent_session` through to each fired spawn
  (check KiroCrew changelog / source — unknown as of 2026-10-09). If not supported,
  alternative: use a `schedule(delay=interval)` one-shot dispatch into the member slot,
  with Raven rescheduling itself at the end of each check-in.
- [ ] 3.3 Run unit tests
- [ ] 3.4 Re-run smoke test on a fresh crew
