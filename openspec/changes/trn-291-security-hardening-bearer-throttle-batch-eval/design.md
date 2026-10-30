# Design

## Context

See proposal.md — Why for motivation.

Three concrete hardening items from the 2026-10-30 review report:

**H-5 (bearer throttle):** `BearerAuthMiddleware._dispatch_authenticated` currently
calls `hmac.compare_digest` on every request and emits a 401 on mismatch, with no
per-IP failure accumulation. An attacker who can send arbitrary requests can guess
bearer tokens at the rate the transport will service them. The existing
`security.Throttle` primitive is already used for dashboard login (`dashboard.py`
`DashboardGate`) and has the right interface — keyed on `(account, source)`,
sliding-window, resets on success.

**H-3 (batch status persistence):** `_dispatch_batch` (lifecycle.py) calls
`_write_batch` twice: once on success (status `"pending"`) and once on partial
failure (status `"partial"`), both as a whole-batch record. The batch entry's
`status` advances to `"complete"` only when `_pickup_batch` drains all tasks and
calls `update_batch_status`. Between dispatch and full pickup completion, there is
no per-task progress visible in the registry — a caller that dies between dispatch
and pickup cannot resume with partial-progress knowledge. The `_task_timestamps`
dict (already per-task) is the right place to add a `status` field, since it is the
source of truth consulted by pickup.

**H-2 (eval doc):** `install.sh` evals `$_RESOLVED`, the output of
`yaml_config.py`. The script is a first-party vendored helper, so the output is
trusted; but that trust assumption is not documented inline, making the pattern
look unsafe to future readers who may not trace the call chain. A targeted
comment block is all that is needed; a refactor to `export`/`source` is
feasible in principle but would require changes to how `yaml_config.py` formats
its output and is out of scope for this change.

---

## Goals / Non-Goals

**Goals:**
- Add a per-IP failure throttle to bearer auth that returns 429 after repeated
  failures and resets on a valid token.
- Record per-task `status` in `_task_timestamps` as each task in a batch
  completes, making partial progress visible.
- Document the `eval "$_RESOLVED"` trust assumption inline in `install.sh`.
- Unit tests for bearer throttle integration.

**Non-Goals:**
- Persisting throttle state across process restarts (in-memory is acceptable,
  consistent with `RateLimiter` and the dashboard `Throttle`).
- Exposing per-task batch status via a new API endpoint (out of scope; pickup
  already surfaces per-task results).
- Refactoring `eval` to `export`/`source` in install.sh.
- Changing the `batch-dispatch` spec (no new requirements — this is an
  implementation hardening of existing behaviour).

---

## Decisions

### D1 — H-5: Where to instantiate the throttle

**Chosen:** Instantiate `_security.Throttle` as an instance attribute of
`BearerAuthMiddleware` in `__init__`, defaulting to `max_failures=10,
window_secs=300` (10 failures per 5-minute window). This follows the exact
pattern used by `DashboardGate._throttle`.

**Why not a module-level singleton:** Module-level state makes tests harder to
isolate (shared across test cases). Instance attribute means each middleware
instance gets a fresh throttle, consistent with `DashboardGate`.

**Why not `RateLimiter`:** `RateLimiter` tracks request volume (all requests,
regardless of outcome). We want to track only *failed auth attempts*, which is
precisely what `Throttle` models. `RateLimiter` would penalise legitimate callers
for high request volume, not for repeated failures.

**Parameters — rationale:**
- `max_failures=10`: higher than the dashboard (5) because MCP callers may be
  automated and a one-off misconfiguration could trigger a lockout; but low enough
  to stop online guessing within a window.
- `window_secs=300`: 5-minute sliding window, consistent with `POST /login` rate
  limit.
- Both values should be overridable via `GA_BEARER_THROTTLE_MAX_FAILURES` and
  `GA_BEARER_THROTTLE_WINDOW_SECS` env vars, read at `__init__` time (same
  pattern as `_parse_rate_limit_var`).

### D2 — H-5: Throttle key — source IP only

**Chosen:** Key on source IP only (not `account + source`), using the existing
`_request_source(scope)` helper already in `auth.py`.

**Why not account+source:** There is no account identifier in bearer auth — the
token *is* the credential, and we must not store even a hash of a presented token
in the throttle key (the token value must not be retained on failure paths).
Source IP is the only stable, pre-auth identifier available.

**XFF handling:** Use `_request_source(scope)` directly. This reads `X-Forwarded-For`
header first then falls back to ASGI client IP — consistent with the audit path
in `_reject`. Throttle keying should be conservative (same as existing audit
source extraction). A future TRN can add trusted-proxy CIDR awareness if needed.

### D3 — H-5: 429 vs 401 — response code on lockout

**Chosen:** Return 429 (Too Many Requests) with `Retry-After: {window_secs}`
header when the throttle is locked. Continue returning 401 for individual failures
within the window.

**Why 429 not 401:** Returning 401 for both failure and lockout is ambiguous —
the client cannot tell whether to retry with a corrected token or wait. 429 with
`Retry-After` gives the client and operator an unambiguous signal. Consistent with
`RateLimitMiddleware` response code.

**Check order in `_dispatch_authenticated`:**
```
1. if throttle locked for source IP → 429 (before touching the token)
2. parse + compare token
3. if mismatch → throttle.record_failure(source) → 401
4. if match → throttle.record_success(source) → proceed
```
Checking the throttle *before* the HMAC compare avoids a timing oracle (same
rationale as `DashboardGate.handle_login_post`).

### D4 — H-3: Per-task status in `_task_timestamps`

**Chosen:** Add a `status` field to each task's entry in `_task_timestamps` when
`_dispatch_batch` dispatches it (`"pending"`) and update it to `"complete"` when
pickup confirms the task is done.

The actual update-on-completion belongs in `_pickup_batch` (lifecycle.py), which
already iterates per-task results and calls `update_batch_status` for the whole
batch. Adding a per-task status write there keeps the change contained to
lifecycle.py and registry.py.

**Concurrency:** `_task_timestamps` is already guarded by `_task_timestamps_lock`;
per-task status writes use the same lock path.

**Why not a separate `_task_statuses` dict:** Keeping it in `_task_timestamps`
avoids adding a third global dict with its own lock. The `_task_timestamps` dict
is already the per-task source of truth for pickup responses.

**No new API surface:** Per-task status is readable via the existing `pickup` tool
response (the `status` field is already included in per-task result dicts when
present). No new endpoint is required.

### D5 — H-2: eval comment text and scope

**Chosen:** Insert a comment block immediately above the `eval "$_RESOLVED"` line
(and its sibling in the `else` branch) explaining:
1. What `$_RESOLVED` contains (shell-quoted KEY=value lines from `yaml_config.py`).
2. Why this is safe: the Python helper is a vendored first-party script; it reads
   only the YAML config file path(s) passed by the script itself; no user-supplied
   string is interpolated into the helper's output.
3. That a future refactor to `source <(...)` or per-variable `export` is the safer
   alternative when the config output format stabilises.

The comment applies to both `eval` sites (the `--config` branch and the implicit
repo+XDG branch) — both call the same helper with the same trust properties.

**Why not refactor now:** `yaml_config.py` emits `KEY='value'` lines designed for
`eval`. Switching to a different output format (e.g., a sourceable file or
structured JSON for per-variable export) requires changes to the Python helper and
all callers. That is a separate change with migration risk; documentation is the
right scope for this item.

---

## Data Flow

### H-5: Bearer throttle in `_dispatch_authenticated`

```
request arrives at BearerAuthMiddleware._dispatch_authenticated
│
├─ [self._key empty] → skip throttle, fall through (no-auth mode)
│
├─ [path in _PUBLIC_PATHS] → skip throttle, fall through
│
├─ source_ip = _request_source(scope)
├─ throttle.is_locked("bearer", source_ip) ?
│   └─ YES → send 429 + Retry-After: {window_secs}  ← NEW
│
├─ parse Authorization header → token
├─ hmac.compare_digest(token, self._key) ?
│   ├─ FAIL → throttle.record_failure("bearer", source_ip)
│   │         → send 401                             ← record_failure NEW
│   └─ PASS → throttle.record_success("bearer", source_ip)
│             → dispatch to routes / downstream      ← record_success NEW
```

### H-3: Per-task status in `_dispatch_batch` / `_pickup_batch`

```
_dispatch_batch
  loop over tasks:
    spawn task → get tid
    _task_timestamps[tid] = {created_at, started_at: None,
                              completed_at: None, status: "pending"}  ← NEW

_pickup_batch (poll round)
  for tid in task_ids:
    res = pickup_single(tid, timeout=0)
    if res.get("done"):
      with _task_timestamps_lock:
        if tid in _task_timestamps:
          _task_timestamps[tid]["status"] = "complete"               ← NEW
          _task_timestamps[tid]["completed_at"] = now()              ← NEW (if absent)
```

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Throttle locks out a legitimate automated caller sharing an IP with an attacker | `max_failures=10` gives headroom; env-var override allows operators to tune |
| `_request_source` returns `None` (unknown IP) | Use `"unknown"` as the throttle key — all anonymous callers share one bucket; acceptable for this posture |
| Per-task status write under lock contends with pickup reads | `_task_timestamps_lock` is already held per-task in the existing code; the new write is a single dict update, same latency as the existing timestamp writes |
| Comment in install.sh goes stale if the helper changes | Comment references the helper by name (`yaml_config.py`) and describes the invariant, not the implementation |
