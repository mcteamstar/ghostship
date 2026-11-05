# Design

## Context

See proposal.md — Why for motivation.

The three env vars live in `transport/lifecycle.py` at different points:

| Var | Location | How read |
|:----|:---------|:---------|
| `GA_TASK_TIMESTAMP_TTL_SECS` | line ~350, module-level | `float(os.environ.get(..., "3600"))` — no error handling |
| `GA_PICKUP_MAX_POLL_SECS` | line ~2757, module-level | `int(os.environ.get(..., "30"))` — no error handling |
| `GA_BATCH_MAX_TASKS` | line ~2924, per-call inside `_dispatch_batch()` | manual `try/except` with inline `ConfigError` import |

`Config.from_env()` in `transport/config.py` already has `_env_float()` and `_env_int()` helpers
that raise `ConfigError` with a descriptive message on bad input, and a suite of existing fields
that follow the `GA_FOO → cfg.ga_foo` naming convention.

## Goals / Non-Goals

**Goals:**
- All three vars parsed once at startup via `Config.from_env()`, raising `ConfigError` with a
  clear message on non-numeric input.
- `lifecycle.py` reads `cfg.ga_task_timestamp_ttl_secs`, `cfg.ga_pickup_max_poll_secs`, and
  `cfg.ga_batch_max_tasks` in place of the current `os.environ.get` reads.
- Tests can construct `Config(ga_batch_max_tasks=5)` directly without env mutation.

**Non-Goals:**
- Changing the defaults (3600 / 30 / 20) or the semantics of any field.
- Moving other module-level lifecycle constants into Config (separate scope).

## Decisions

**Use existing `_env_int` / `_env_float` helpers — no new helper needed.**
Both helpers already exist in `config.py` and handle the `ConfigError` pattern. `_env_float` for
`GA_TASK_TIMESTAMP_TTL_SECS`, `_env_int` for the other two.

**Module-level constants → `cfg.*` reads.**
`_TASK_TIMESTAMP_TTL_SECS` and `GA_PICKUP_MAX_POLL_SECS` are currently module-level constants
(read once at import). After the change they will be read from the `cfg` singleton — behaviour
is identical since `cfg` is also built once at startup. The per-call `os.environ.get` in
`_dispatch_batch` becomes `cfg.ga_batch_max_tasks` (already a resolved int, no try/except needed).

**Retain the existing module-level names as thin aliases if needed for clarity.**
The private name `_TASK_TIMESTAMP_TTL_SECS` is only used in one function
(`_evict_old_task_timestamps`). Replace the usage directly rather than keeping an alias.

## Risks / Trade-offs

**[Startup fail-fast] Bad env var now crashes at startup, not lazily.**
For `GA_BATCH_MAX_TASKS`, the current code only raises on the first batch dispatch call. After
this change, a bad value crashes the transport at startup. This is strictly better — fail fast
with a clear error rather than silently accepting the config and failing on first use.

**[Circular import] `lifecycle.py` already imports from `config.py` — no new dependency.**
`from config import Config` is already present. Adding three fields to `Config` introduces no new
import edges.
