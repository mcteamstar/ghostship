## 1. Config

- [x] 1.1 Add `ga_dashboard_default: bool = False` to the config dataclass in `transport/config.py`
- [x] 1.2 Read from `GA_DASHBOARD_DEFAULT` env var (default `false`)

## 2. launch() — honour site default

- [x] 2.1 Change `launch()` parameter from `dashboard: bool = False` to `dashboard: bool | None = None` in `transport/server.py`
- [x] 2.2 Resolve effective value: `effective_dashboard = dashboard if dashboard is not None else cfg.ga_dashboard_default`
- [x] 2.3 Replace all uses of `dashboard` in the `launch()` body with `effective_dashboard`
- [x] 2.4 Update `launch()` docstring: `None` (default) uses `GA_DASHBOARD_DEFAULT`; `True`/`False` overrides it

## 3. install.sh + docs

- [x] 3.1 Add `# GA_DASHBOARD_DEFAULT=false` (commented) to the compose template in `scripts/install.sh`
- [x] 3.2 Add `GA_DASHBOARD_DEFAULT` row to the environment variables table in `docs/configuration.md`

## 4. Tests

- [x] 4.1 Unit: `GA_DASHBOARD_DEFAULT=false`, no explicit arg → effective_dashboard is False
- [x] 4.2 Unit: `GA_DASHBOARD_DEFAULT=true`, no explicit arg → effective_dashboard is True
- [x] 4.3 Unit: `GA_DASHBOARD_DEFAULT=true`, `dashboard=False` explicit → effective_dashboard is False
- [x] 4.4 Unit: `GA_DASHBOARD_DEFAULT=false`, `dashboard=True` explicit → effective_dashboard is True
- [x] 4.5 Run full unit suite

## 5. Verification

- [ ] 5.1 `python3 -m py_compile transport/server.py transport/config.py` — syntax clean
- [ ] 5.2 Set `GA_DASHBOARD_DEFAULT=true` in academy ghostship.conf, deploy, launch a crew → confirm `dashboard_url` is non-null
