# Tasks

## 1. Add fields to Config dataclass

- [ ] 1.1 In `transport/config.py`, add three fields to the `Config` dataclass:
  `ga_task_timestamp_ttl_secs: float` (default `3600.0`, via `_env_float`),
  `ga_pickup_max_poll_secs: int` (default `30`, via `_env_int`),
  `ga_batch_max_tasks: int` (default `20`, via `_env_int`).
  Verify: `python -c "from transport.config import Config; c = Config.from_env(); print(c.ga_batch_max_tasks)"` prints `20`.

- [ ] 1.2 Add unit tests in `tests/unit/test_config.py` (or the existing config test module)
  covering: correct defaults for all three fields; `ConfigError` raised for a non-numeric value
  for each field; `Config(ga_batch_max_tasks=5)` constructs without env access.
  Verify: `pytest tests/unit/test_config.py -v -k "batch_max or pickup_max or task_timestamp"` passes.

## 2. Update lifecycle.py

- [ ] 2.1 Remove the module-level line `_TASK_TIMESTAMP_TTL_SECS = float(os.environ.get(...))` and
  replace the single usage in `_evict_old_task_timestamps` with `cfg.ga_task_timestamp_ttl_secs`.
  Verify: `grep -n "_TASK_TIMESTAMP_TTL_SECS" transport/lifecycle.py` returns no results.

- [ ] 2.2 Remove the module-level line `GA_PICKUP_MAX_POLL_SECS = int(os.environ.get(...))` and
  replace all usages in `_pickup_batch` with `cfg.ga_pickup_max_poll_secs`.
  Verify: `grep -n "GA_PICKUP_MAX_POLL_SECS" transport/lifecycle.py` returns no results.

- [ ] 2.3 In `_dispatch_batch`, replace the manual `_raw_max_tasks = os.environ.get(...)` /
  `int(...)` / `ConfigError` block with `max_tasks = cfg.ga_batch_max_tasks`.
  Verify: `grep -n "GA_BATCH_MAX_TASKS" transport/lifecycle.py` returns no results.

## 3. Regression check

- [ ] 3.1 Run the full unit test suite: `pytest tests/unit/ -q` — no failures.

## Workflow follow-up

- Assimilate the change after the PR is merged.
