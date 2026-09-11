## Why

`launch()` hardcodes `dashboard=False` as its default. There is no way to change this site-wide — every agent must pass `dashboard=True` explicitly on each `launch()` call, or the operator must update the skill. Now that `slot` defaults to `"bridge"` when a dashboard is active (TRN-147), enabling dashboard by default unlocks full visibility for all dispatched tasks with zero per-call configuration.

## What Changes

- Add `GA_DASHBOARD_DEFAULT` environment variable (boolean, default `false`)
- When `GA_DASHBOARD_DEFAULT=true`, the effective dashboard value for `launch()` is `True` unless the caller explicitly passes `dashboard=False`
- Add to `scripts/install.sh` compose template (commented out)
- Document in `docs/configuration.md`

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `crew-lifecycle`: `launch()` gains a site-wide default for the `dashboard` parameter via `GA_DASHBOARD_DEFAULT`

## Impact

- `transport/config.py` — add `ga_dashboard_default: bool = False`
- `transport/server.py` — in `launch()`, resolve effective dashboard as `dashboard or cfg.ga_dashboard_default`
- `scripts/install.sh` — add `GA_DASHBOARD_DEFAULT` to compose template (commented, default false)
- `docs/configuration.md` — document the new variable
- No breaking changes — existing callers unaffected when `GA_DASHBOARD_DEFAULT` is unset
