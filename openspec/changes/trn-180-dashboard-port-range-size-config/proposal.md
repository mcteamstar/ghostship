## Why

`GA_DASHBOARD_PORT_RANGE_SIZE` is hardcoded as the integer literal `1024` in
`transport/config.py:from_env()` — it is never read from the environment despite the
matching `ga_dashboard_port_range_size` field on the `Config` dataclass having a
default of `1024`. Operators cannot override the port range size without editing source
code. This is inconsistent with `GA_DASHBOARD_PORT_RANGE_START`, which is correctly
read from the environment. The fix is a one-liner: replace the literal with
`_env_int("GA_DASHBOARD_PORT_RANGE_SIZE", "1024")`.

## What Changes

- In `transport/config.py` `from_env()`: replace the hardcoded `1024` with
  `_env_int("GA_DASHBOARD_PORT_RANGE_SIZE", "1024")`
- Add `GA_DASHBOARD_PORT_RANGE_SIZE` to `config/ghostship.conf.example` alongside
  `GA_DASHBOARD_PORT_RANGE_START`
- Add a unit test asserting the env var is read correctly (default and override)

## Capabilities

### New Capabilities
None.

### Modified Capabilities
None — this makes the existing config field actually honour the env var it was
always supposed to read. No spec-level behaviour changes; `skip_specs: true` is set.

## Impact

- `transport/config.py` — one-line change in `from_env()`
- `config/ghostship.conf.example` — add commented entry
- `tests/unit/test_config_from_env.py` — add test
