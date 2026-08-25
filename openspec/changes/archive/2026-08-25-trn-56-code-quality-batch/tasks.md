## 1. Idle monitor fail-open

- [x] 1.1 In `_idle_monitor` (transport/server.py), change both `except Exception: pass` blocks (the `/api/spawn` check and the `/api/crons` check) to `except Exception: continue`, and treat non-success responses as unknown activity, so a transient API error skips the crew rather than falling through to the stop path.
- [x] 1.2 Add a unit test asserting that when `/api/spawn` raises an exception or returns a non-success or malformed response, the idle monitor does not call `container_stop` for that crew.
- [x] 1.3 Add a unit test asserting the same for the `/api/crons` exception, non-success, or malformed response path.

## 2. HMAC scope — Subject + From headers

- [x] 2.1 In `_format_captain_mail` (transport/server.py), change the HMAC input from `body.encode()` to `f"Subject:{subject}\nFrom:admiral@localhost\n\n{body}".encode()`.
- [x] 2.2 Update `crews/_base/orientation/verify-admiral-sig` to compute the HMAC over the same `Subject:<subject>\nFrom:admiral@localhost\n\n<body>` payload. Extract Subject and From from the message headers when verifying.
- [x] 2.3 Add a round-trip unit test: sign a message with `_format_captain_mail`, extract the `X-Admiral-Sig` header, and verify it against the new payload format.

## 3. Magic string constants

- [x] 3.1 Add three module-level constants near the top of transport/server.py: `CREW_CONTAINER_PREFIX = "gs-"`, `CREW_VOLUME_PREFIX = "gs-vol-"`, `CREW_HOME_VOLUME_PREFIX = "gs-home-"`.
- [x] 3.2 Replace all bare string literals `"gs-"`, `"gs-vol-"`, `"gs-home-"` in `nuke`, `_cleanup_crew`, `_ensure_crew_running`, and any other uses with the constants.

## 4. _startup_events pruning

- [x] 4.1 Confirm the `finally` block in the leader path of `_ensure_crew_running` unconditionally pops `crew_id` from `_startup_events` and calls `event.set()` — no code change needed if correct, just verify.
- [x] 4.2 Add a unit test that mocks the leader path to raise mid-restart and asserts `crew_id` is no longer in `_startup_events` after the exception.

## 5. Flaky test fix

- [x] 5.1 In `test_cron_branch` (tests/unit/test_transport.py), replace the `assertGreater(job["next_fire_at"], now + 60)` assertion with one that is not time-of-minute sensitive — assert that `abs(job["next_fire_at"] - (now + 60)) > 1` (i.e., the result is not the fallback `now+60` value) OR compute the expected croniter value directly and assert equality.

## 6. Verification

- [x] 6.1 Run `bash tests/run.sh --unit` and confirm all tests pass.
- [x] 6.2 Run `test_cron_branch` in isolation at a simulated HH:59 time to confirm it no longer fails near hour boundaries.
