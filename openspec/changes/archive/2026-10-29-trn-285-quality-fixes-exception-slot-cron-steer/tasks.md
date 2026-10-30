## 1. M-1 — Extend scrypt except clause

- [x] 1.1 In `transport/security.py`, locate `verify_password()`. Find the scrypt
  branch's `except (ValueError, TypeError):` clause and extend it to
  `except (ValueError, TypeError, OSError, OverflowError):`.
- [x] 1.2 Add a unit test to `tests/unit/test_security.py`: mock `hashlib.scrypt`
  to raise `OSError` and assert `verify_password()` returns `False` without raising.
  Repeat for `OverflowError`.

## 2. M-2 — slot=True warning guard

- [x] 2.1 In `transport/lifecycle.py`, locate `_resolve_dispatch_slot()`. Add a guard
  at the top: if `slot is True`, log a WARNING and set `slot = None`.
- [x] 2.2 Add a unit test to `tests/unit/test_lifecycle.py`: call a dispatch with
  `slot=True` and assert (a) a warning is logged and (b) the dispatch proceeds as
  if `slot=None` was passed (i.e. member-slot or headless resolution proceeds normally).

## 3. M-3 — Cron captain first-fire from expression

- [x] 3.1 In `transport/captain_engine.py`, locate `_captain_do_order()` and find
  the `next_fire_at: now + 60` line.
- [x] 3.2 Check whether `croniter` is already imported in `captain_engine.py` or
  available via the existing `advance_next_fire_at` helper in `registry.py`. Use
  whichever is available to evaluate the cron expression.
- [x] 3.3 Implement: if `effective_cron` is set, compute `next_fire_at` as the next
  cron tick after `now`; otherwise keep `now + 60`.
- [x] 3.4 Add a unit test to `tests/unit/test_captain_engine.py`:
  - Call `_captain_do_order` with `cron="0 9 * * *"` at a known time (e.g. 08:00)
  - Assert `next_fire_at` is approximately the next 09:00, not `now + 60`
- [x] 3.5 Add a unit test confirming interval schedules still use 60s initial delay.

## 4. M-4 — httpx status-code error classification

- [x] 4.1 In `transport/captain_engine.py`, locate `_steer_captain_checkin()` and
  find the string-matching error classification (`"400 Bad Request" in err_str`).
- [x] 4.2 Replace with `except httpx.HTTPStatusError as exc:` checking
  `exc.response.status_code == 400` and `exc.request.url.path.endswith("/continue")`.
  Ensure the fallthrough `except Exception` still handles other errors.
- [x] 4.3 Add a unit test: mock `_crew_api` to raise `httpx.HTTPStatusError` with
  `status_code=400` on a `/continue` URL; assert the steer fallback is triggered.
- [x] 4.4 Add a unit test: mock `_crew_api` to raise `httpx.HTTPStatusError` with
  `status_code=500`; assert the error is propagated (not treated as a continue-400).

## 5. Verification

- [x] 5.1 Run `bash scripts/run.sh --unit` — all tests pass.
- [x] 5.2 Confirm no new lint/type errors introduced.
