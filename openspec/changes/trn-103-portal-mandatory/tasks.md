## 1. Remove GA_PORTAL_ENABLED from config and server

- [x] 1.1 Remove `ga_portal_enabled` field from `Config` dataclass in `transport/config.py`
- [x] 1.2 Remove `ga_portal_enabled=_env_bool_default_off("GA_PORTAL_ENABLED")` from `from_env()`
- [x] 1.3 Remove `GA_PORTAL_ENABLED = cfg.ga_portal_enabled` from `transport/server.py`
- [x] 1.4 Remove all `if GA_PORTAL_ENABLED:` guards in `server.py` — take the portal-enabled branch unconditionally in each case
- [x] 1.5 Remove the `launch(dashboard=True)` error guard that checked `not GA_PORTAL_ENABLED`

## 2. Update install.sh

- [x] 2.1 Remove `GA_PORTAL_ENABLED=false` default and any `--portal-enabled` CLI flag
- [x] 2.2 Make the `ga-portal` service stanza unconditional (remove the `if GA_PORTAL_ENABLED` wrapper)
- [x] 2.3 Make the Caddyfile generation unconditional
- [x] 2.4 Make `ga-portal-data` volume unconditional
- [x] 2.5 Simplify the portal health check (no conditional)

## 3. Docs and config

- [x] 3.1 Remove `GA_PORTAL_ENABLED` from `config/ghostship.conf.example` (with migration comment)
- [x] 3.2 Remove `GA_PORTAL_ENABLED` row from `docs/configuration.md`
- [x] 3.3 Update `docs/caddy.md` — remove opt-in framing; portal is always on
- [x] 3.4 Add breaking-change note to `CHANGELOG.md`

## 4. Tests

- [x] 4.1 Remove tests that patch `GA_PORTAL_ENABLED=False` to test the disabled code path — those paths no longer exist
- [x] 4.2 Update remaining tests that patch `GA_PORTAL_ENABLED=True` — replace with no patch (portal is always enabled)
- [x] 4.3 Run `tests/run.sh --unit` — all tests pass
