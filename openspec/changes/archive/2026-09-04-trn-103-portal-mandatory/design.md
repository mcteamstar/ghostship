## Context

See proposal.md. This is a cleanup change — no new behaviour, just removal of dead code.

## What to remove

**`transport/config.py`**
- `ga_portal_enabled: bool = False` field from `Config`
- `ga_portal_enabled=_env_bool_default_off("GA_PORTAL_ENABLED")` from `from_env()`

**`transport/server.py`**
- `GA_PORTAL_ENABLED = cfg.ga_portal_enabled` module-level assignment
- All `if GA_PORTAL_ENABLED:` / `if not GA_PORTAL_ENABLED:` / `if GA_PORTAL_ENABLED is False:` guards — take the portal-enabled branch unconditionally
- The `launch(dashboard=True)` error path that checked `not GA_PORTAL_ENABLED` — remove the check; portal is always available
- Any health check or log message that conditionally mentions portal being enabled/disabled

**`scripts/install.sh`**
- `GA_PORTAL_ENABLED=false` default and CLI flag `--portal-enabled`
- `$(if [[ "${GA_PORTAL_ENABLED:-false}" == "true" ]]; then ...)` wrappers around the portal service stanza and Caddyfile generation — make them unconditional
- `$(if [[ "${GA_PORTAL_ENABLED:-false}" == "true" ]]; then printf 'volumes:\n  ga-portal-data:\n'; fi)` — always emit the volume
- Health check: simplify (no conditional on portal being enabled)

**Docs and config**
- `config/ghostship.conf.example`: remove `GA_PORTAL_ENABLED` section; keep `GA_PORTAL_TLS_MODE` etc.
- `docs/configuration.md`: remove the `GA_PORTAL_ENABLED` row from the table
- `docs/caddy.md`: remove all "opt-in" / `GA_PORTAL_ENABLED=true` framing

## What to keep

All other `GA_PORTAL_*` vars stay — they configure how portal behaves, not whether it runs.

The `_caddy_register_crew` / `_caddy_deregister_crew` calls stay — they now execute unconditionally.

## Migration note

The `install.sh` rebuild path handles all existing deployments. No data migration.
