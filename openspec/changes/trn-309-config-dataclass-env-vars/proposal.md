# Proposal

## Why

Three environment variables are read outside `Config.from_env()` at module import time or
per-call in `transport/lifecycle.py`, bypassing the Config dataclass pattern established for all
other transport env vars. This means they receive no validation, no consistent error handling, and
cannot be overridden in tests without environment mutation. A non-numeric value causes an
unhandled `ValueError` / `ConfigError` that crashes the transport with no clear error message.

## What Changes

- Add `ga_task_timestamp_ttl_secs: float`, `ga_pickup_max_poll_secs: int`, and
  `ga_batch_max_tasks: int` fields to the `Config` dataclass in `transport/config.py`, parsed
  via the existing `_env_float` / `_env_int` helpers with `ConfigError` on bad input.
- Replace the three module-level / per-call `os.environ.get(...)` reads in
  `transport/lifecycle.py` with `cfg.ga_task_timestamp_ttl_secs`,
  `cfg.ga_pickup_max_poll_secs`, and `cfg.ga_batch_max_tasks`.
- Update `docs/configuration.md` to note that all three vars are now validated at startup
  (already documented in the env var table).

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

_(none — env var semantics and defaults are unchanged; this is a pure structural refactor.
No spec-level requirements change.)_

## Impact

- `transport/config.py` — three new fields in `Config` dataclass
- `transport/lifecycle.py` — three `os.environ.get` reads replaced with `cfg.*` reads
- `tests/unit/` — new Config test cases for the three fields
