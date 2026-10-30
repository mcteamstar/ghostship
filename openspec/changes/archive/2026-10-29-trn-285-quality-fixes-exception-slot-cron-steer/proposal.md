# Proposal

## Why

Four MEDIUM quality/correctness findings from the indy-0.10.0 review. All are small,
targeted fixes with low risk and clear correct answers. M-1 is a latent security
edge-case; M-2/M-3/M-4 are correctness issues in the captain and dispatch paths.

## What Changes

### M-1 — `verify_password()` missing `OSError`/`OverflowError` (`security.py`)

The scrypt branch of `verify_password()` catches `(ValueError, TypeError)` but not
`OSError` (raised when `maxmem` is exceeded) or `OverflowError` (raised when hash
parameters overflow C integer bounds). A crafted stored hash with extreme `n`/`r`/`p`
values could cause an unhandled exception in the authentication path, producing a 500
instead of a clean False.

**Fix:** Extend the except clause to `(ValueError, TypeError, OSError, OverflowError)`.

### M-2 — `slot=True` silently falls through to headless dispatch (`lifecycle.py`)

`_resolve_dispatch_slot()` type annotation admits `bool | None`. `slot=True` is
documented as invalid (only `None`, `False`, or a string slug are valid), but it
silently produces headless behaviour. Callers passing `slot=True` by mistake get no
warning and no slot routing — a silent correctness bug.

**Fix:** Add an explicit guard: if `slot is True`, log a warning and treat as `None`
(or raise `ValueError` — decision for design phase).

### M-3 — Cron captain first fire always 60s (`captain_engine.py`)

`_captain_do_order()` hardcodes `next_fire = now + 60` for the first fire regardless
of whether the schedule is interval-based or cron-based. A cron schedule of
`"0 9 * * *"` (daily at 09:00) will still fire 60 seconds after ordering instead of
at the next cron tick.

**Fix:** For cron schedules, evaluate the cron expression to find the next tick after
`now` rather than hardcoding 60s. Interval schedules keep the 60s initial delay.

### M-4 — Fragile string-matching in `_steer_captain_checkin` (`captain_engine.py`)

Error classification uses `"400 Bad Request" in err_str` and `"/continue" in err_str`
— fragile if httpx changes its error message format. The correct pattern (catching
`httpx.HTTPStatusError` and checking `status_code` + URL path) is already used in
`_crew_api_with_recovery` at line 830.

**Fix:** Replace string-matching with `except httpx.HTTPStatusError as exc:` checking
`exc.response.status_code == 400` and `"/continue" in exc.request.url.path`.

## Capabilities

### Modified Capabilities

- `crew-lifecycle`: `slot=True` guard in `_resolve_dispatch_slot`
- `captain`: Cron first-fire evaluation; steer error classification

## Impact

- `transport/security.py` — M-1: extend except clause
- `transport/lifecycle.py` — M-2: slot=True guard
- `transport/captain_engine.py` — M-3: cron first-fire; M-4: httpx error pattern
- `tests/unit/test_security.py` — M-1 regression test
- `tests/unit/test_captain_engine.py` — M-3/M-4 regression tests
- `tests/unit/test_lifecycle.py` — M-2 regression test
