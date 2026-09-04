## Why

`ga-portal` (Caddy) is now a required architectural component — it owns port 80/443, all dashboard ports, and the `portal → transport → crew` proxy path that TRN-102 established. Dashboard access already requires portal as a hard precondition. The `GA_PORTAL_ENABLED` opt-in flag is vestigial: the mode it disables (`GA_PORTAL_ENABLED=false`) no longer provides any useful functionality and introduces dead code paths and test burden.

## What Changes

- **BREAKING**: `GA_PORTAL_ENABLED` is removed. `ga-portal` is always started by `install.sh`. Operators on `GA_PORTAL_ENABLED=false` installs must re-run `install.sh` to upgrade.
- Remove `GA_PORTAL_ENABLED` from `transport/config.py` (`Config` dataclass, `from_env()`), and the module-level assignment in `server.py`.
- Remove all `if GA_PORTAL_ENABLED:` / `if not GA_PORTAL_ENABLED:` guards in `server.py` — `_caddy_register_crew` and `_caddy_deregister_crew` are unconditional.
- `scripts/install.sh`: always generate the `ga-portal` service stanza and Caddyfile; remove `if GA_PORTAL_ENABLED` conditionals.
- Remove `GA_PORTAL_ENABLED` from `config/ghostship.conf.example`, `docs/configuration.md`, `docs/caddy.md`.
- Keep all other `GA_PORTAL_*` vars (`GA_PORTAL_TLS_MODE`, `GA_PORTAL_DOMAIN`, `GA_PORTAL_PORT`, `GA_PORTAL_HTTP_PORT`, `GA_PORTAL_SESSION_TTL_SECS`, `GA_PORTAL_ADMIN_URL`) — these configure portal behaviour and remain.
- Update `CHANGELOG.md` with the breaking change and migration note.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/caddy-proxy`: `ga-portal` is always present; `GA_PORTAL_ENABLED` guard removed. The spec no longer describes an opt-in mode.
- `transport/dashboard-proxy`: Dashboard access no longer requires checking `GA_PORTAL_ENABLED`; it is always available (assuming `ga-portal` started correctly).

## Impact

- `transport/server.py`, `transport/config.py` — remove flag and guards
- `scripts/install.sh` — always generate portal service and config
- `config/ghostship.conf.example`, `docs/configuration.md`, `docs/caddy.md`, `docs/dashboard-proxy.md` — remove `GA_PORTAL_ENABLED` references
- Tests — remove `GA_PORTAL_ENABLED=False` code paths; update tests that patch the flag
- **BREAKING** — re-run `install.sh` required on any existing deployment
