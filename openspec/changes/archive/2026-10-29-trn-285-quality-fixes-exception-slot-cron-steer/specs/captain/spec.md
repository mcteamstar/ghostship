## MODIFIED Requirements

### Requirement: Cron captain schedule evaluates first fire from cron expression

When `_captain_do_order()` creates a new captain schedule with a cron expression,
the initial `next_fire_at` SHALL be derived by evaluating the cron expression against
the current time, not hardcoded to `now + 60`. Interval-based schedules SHALL
continue to use the 60-second initial delay.

#### Scenario: Cron schedule fires at next cron tick, not 60s
- **WHEN** `captain(action="order", cron="0 9 * * *")` is called at 08:00 UTC
- **THEN** the first `next_fire_at` is the next 09:00 UTC, not 08:01 UTC

#### Scenario: Interval schedule retains 60s initial delay
- **WHEN** `captain(action="order", interval=3600)` is called
- **THEN** the first `next_fire_at` is approximately `now + 60s`

### Requirement: _steer_captain_checkin classifies errors by HTTP status code

`_steer_captain_checkin` SHALL classify `httpx.HTTPStatusError` responses by
inspecting `exc.response.status_code` and `exc.request.url.path`, NOT by
string-matching on the exception message. This makes the classification robust to
changes in httpx error message formatting.

#### Scenario: 400 on /continue path triggers follow-up steer
- **WHEN** the gateway returns HTTP 400 on a `/continue` request in `_steer_captain_checkin`
- **THEN** the transport falls back to a steer (interrupt) call
- **THEN** the classification is performed via `status_code == 400` check on the exception

### Requirement: verify_password handles scrypt resource exceptions

`verify_password()` SHALL return `False` (and not raise) when the scrypt hash
verification raises `OSError` (maxmem exceeded) or `OverflowError` (parameter
overflow). These exceptions join the existing `(ValueError, TypeError)` in the
catch clause.

#### Scenario: Extreme scrypt parameters return False, not exception
- **WHEN** a stored hash has extreme `n`/`r`/`p` values that exceed system scrypt limits
- **THEN** `verify_password()` returns `False`
- **THEN** no exception propagates to the caller
