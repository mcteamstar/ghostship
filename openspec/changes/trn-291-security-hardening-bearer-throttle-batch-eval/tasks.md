# Tasks

## T1: Wire FailureThrottle to BearerAuthMiddleware in transport/auth.py

- [ ] Add env-var readers `GA_BEARER_THROTTLE_MAX_FAILURES` (default `10`) and
  `GA_BEARER_THROTTLE_WINDOW_SECS` (default `300`) — parse in the same style as
  `_parse_rate_limit_var`, emit a WARNING on parse failure and fall back to the
  default.
- [ ] In `BearerAuthMiddleware.__init__`, instantiate
  `self._bearer_throttle = _security.Throttle(max_failures=..., window_secs=...)`
  using the parsed env-var values.
- [ ] In `_dispatch_authenticated`, before parsing the `Authorization` header:
  - Compute `source_ip = _request_source(scope) or "unknown"`.
  - If `self._bearer_throttle.is_locked("bearer", source_ip)` → send HTTP 429
    with `Retry-After: {int(self._bearer_throttle.window_secs)}` and
    `Content-Type: text/plain; charset=utf-8`. Return immediately (do not fall
    through to token comparison).
- [ ] After the `hmac.compare_digest` call:
  - On mismatch: call `self._bearer_throttle.record_failure("bearer", source_ip)`
    before calling `self._reject(send, scope)`.
  - On match: call `self._bearer_throttle.record_success("bearer", source_ip)`
    before dispatching to routes/downstream.
- [ ] The throttle check and failure recording apply only when `self._key` is
  non-empty (i.e., auth is enabled). The no-auth pass-through path is unchanged.
- [ ] The `_PUBLIC_PATHS` bypass (`/health`) is unchanged and does not consult the
  throttle.

## T2: Write per-task batch status to disk in _dispatch_batch (lifecycle.py)

- [ ] In `_dispatch_batch`, when appending a new entry to `_task_timestamps[tid]`
  (the block that runs after a successful `/api/spawn` call), add
  `"status": "pending"` to the dict alongside the existing `created_at`,
  `started_at`, and `completed_at` fields.
- [ ] In `_pickup_batch` (also in `lifecycle.py`), inside `_poll_round`, after
  `res.get("done")` is `True` for a given `tid`:
  - Acquire `_task_timestamps_lock`.
  - If `tid` is in `_task_timestamps`, set `_task_timestamps[tid]["status"] =
    "complete"`.
  - If `_task_timestamps[tid]["completed_at"]` is still `None`, set it to the
    current UTC timestamp (`datetime.now(timezone.utc).isoformat()`).
  - Release lock.
- [ ] Ensure the existing `update_batch_status(crew_id, batch_id, "complete")` call
  (whole-batch level) in `_pickup_batch` is unchanged — it still fires when all
  tasks are done.
- [ ] Do not add a new `status` field to `_write_batch`'s stored dict in
  `registry.py` — per-task status lives in `_task_timestamps` only. The
  registry's batch `status` field (`pending` / `partial` / `complete`) is a
  whole-batch aggregate and is already correct.

## T3: Add trust-assumption comment to eval section in bin/install.sh

- [ ] Immediately above the first `eval "$_RESOLVED"` line (the `--config` branch,
  around line 338), insert this comment block:

  ```bash
  # Trust basis for eval: $_RESOLVED is the stdout of yaml_config.py, a vendored
  # first-party Python helper. Its input is one or more YAML file paths supplied
  # by this script itself — no user-controlled string is interpolated into the
  # helper's output. The output format is shell-quoted KEY='value' lines (produced
  # by shlex.quote) designed for eval. Prefer `source <(...)` or per-variable
  # export if this format is ever refactored.
  ```

- [ ] Insert the same comment block immediately above the second `eval "$_RESOLVED"`
  line (the implicit repo+XDG branch, around line 357).
- [ ] No functional change — comment-only edit. Verify with `bash -n bin/install.sh`
  after the edit.

## T4: Add unit tests for bearer throttle behaviour

Tests belong in `tests/unit/test_auth.py` (or a new file `tests/unit/test_bearer_throttle.py`
if test_auth.py is already large). Follow the existing test patterns in that file.

- [ ] **Test: throttle is inactive when `api_key` is empty** — a request with no
  `Authorization` header against a middleware with `api_key=""` passes through
  without consulting the throttle.
- [ ] **Test: within-limit failures return 401** — fewer than `max_failures`
  requests with a wrong token return HTTP 401 (not 429).
- [ ] **Test: throttle triggers 429 after `max_failures`** — after exactly
  `max_failures` failed attempts from the same source IP, the next attempt returns
  HTTP 429 with a `Retry-After` header. The response body indicates rate limiting,
  not just auth failure.
- [ ] **Test: valid token resets throttle** — after `max_failures - 1` failures, a
  correct token succeeds (200) and a subsequent wrong-token request returns 401
  (not 429), proving `record_success` cleared the counter.
- [ ] **Test: throttle keys on source IP** — failures from IP A do not affect
  requests from IP B (separate ASGI `client` tuples in the scope).
- [ ] **Test: `Retry-After` value matches window** — the `Retry-After` header value
  is the integer ceiling of `window_secs`.
- [ ] **Test: throttle is per-instance** — two separate `BearerAuthMiddleware`
  instances share no throttle state (no module-level singleton).

## T5: Run tests and verify

- [ ] Run `python -m pytest tests/unit/test_auth.py -v` (or the new throttle test
  file) and confirm all new tests pass.
- [ ] Run `python -m pytest tests/unit/ -v` and confirm no existing tests regress.
- [ ] Run `bash -n bin/install.sh` to confirm the install.sh comment edit
  introduced no syntax errors.
- [ ] Run `python -m pytest tests/unit/test_lifecycle.py -v` to confirm batch
  dispatch and pickup tests still pass with the per-task status additions.
