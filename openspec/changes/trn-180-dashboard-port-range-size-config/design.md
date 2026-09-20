## Context

See proposal.md — Why.

In `transport/config.py`, `from_env()` at ~L287:
```python
ga_dashboard_port_range_size=1024,
```

The `Config` dataclass field at ~L161 has `ga_dashboard_port_range_size: int = 1024`.
`GA_DASHBOARD_PORT_RANGE_START` directly above it correctly uses `_env_int(...)`.
The inconsistency is a copy-paste omission from when the field was added.

`server.py` at ~L440 reads `cfg.ga_dashboard_port_range_size` into a module-level
`GA_DASHBOARD_PORT_RANGE_SIZE` constant — the plumbing is correct end-to-end; only
the `from_env()` assignment is broken.

## Goals / Non-Goals

**Goals**
- Wire `GA_DASHBOARD_PORT_RANGE_SIZE` env var through `Config.from_env()`
- Document it in `ghostship.conf.example`
- Add a unit test

**Non-Goals**
- Changing the default value (stays 1024)
- Changing how the value is used downstream (`server.py` is already correct)

## Decisions

**Use `_env_int("GA_DASHBOARD_PORT_RANGE_SIZE", "1024")`** — consistent with all
other integer config fields. No min/max validation beyond what `_env_int` provides
(raises `ConfigError` on non-integer input).

**No validation of the range size value.**
A size of 0 or very large is operator error. The existing behaviour on invalid port
allocation is already handled elsewhere. Keep it simple.

## Risks / Trade-offs

[Risk] An operator who previously relied on the hardcoded 1024 (i.e., all of them)
is unaffected — default is unchanged. No risk.

## Migration Plan

One-line code change + example config update. No deployment steps beyond normal.
