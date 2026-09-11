## Context

See proposal.md — Why. Small change: one config field, one resolution line in `launch()`.

## Goals / Non-Goals

**Goals:** Site-wide default for `dashboard` parameter via `GA_DASHBOARD_DEFAULT`.

**Non-Goals:** Per-composition defaults, dashboard auto-enable on crew restart, any change to the dashboard allocation mechanism itself.

## Decisions

**D1 — Resolve at call time, not schema default**
Keep `dashboard: bool = False` in the tool signature (the MCP schema default stays `false`). Resolve the effective value inside `launch()` before any allocation logic:

```python
effective_dashboard = dashboard or cfg.ga_dashboard_default
```

This preserves the MCP schema as-is — the tool description doesn't need to change — while the site config silently upgrades the default.

**D2 — Caller `False` always wins**
`dashboard=False` passed by the caller must override `GA_DASHBOARD_DEFAULT=true`. The `or` operator in D1 already handles this: `False or True = True`, but since Python's `or` short-circuits, explicit `False` from the caller isn't distinguishable from omitted default `False`. To honour explicit `False`, use `None` as the sentinel:

```python
# launch(crew_id, dashboard=None)  — None means "use site default"
effective_dashboard = dashboard if dashboard is not None else cfg.ga_dashboard_default
```

Change the parameter default to `None` and update the docstring to explain `None` = use site default.

## Implementation Plan

### 1. `transport/config.py`

Add `ga_dashboard_default: bool = False` to the config dataclass and read from `GA_DASHBOARD_DEFAULT` env var.

### 2. `transport/server.py` — `launch()`

Change parameter: `dashboard: bool | None = None`

Resolve effective value early:
```python
effective_dashboard = dashboard if dashboard is not None else cfg.ga_dashboard_default
```

Replace all uses of `dashboard` in the function body with `effective_dashboard`.

Update docstring: `dashboard=None` uses site default (`GA_DASHBOARD_DEFAULT`); `True`/`False` overrides it.

### 3. `scripts/install.sh`

Add to compose template (commented out):
```bash
# GA_DASHBOARD_DEFAULT=false  # Set true to allocate dashboard on every launch
```

### 4. `docs/configuration.md`

Add `GA_DASHBOARD_DEFAULT` row to the environment variables table.
