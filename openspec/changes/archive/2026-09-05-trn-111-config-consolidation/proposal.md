## Why

The config surface has grown to ~50 variables as ghostship evolved, but many of them are internal timing details, staged-rollout flags, or Caddy internals that no operator will ever meaningfully change. 0.3.0 is the right moment to clean up before the surface gets locked in — making the install experience clearer for new users and removing maintenance burden.

## What Changes

- **RENAME** `GA_PORTAL_PORT` → `PORT` — backwards compatible with pre-portal installs. Caddy now owns the only port users connect to; `PORT` is the universal convention and is already in the config-file spec precedence chain.
- **REMOVE** `HOST` — container bind interface; always `0.0.0.0` inside a container. Hardcode.
- **REMOVE** `GA_PORTAL_ADMIN_URL` — Caddy admin API address inside the compose network; always `http://ga-portal:2019`. Hardcode.
- **REMOVE** `GA_FILE_TTL_SECS` — presigned URL TTL; 5 minutes is correct for everyone. Hardcode 300.
- **REMOVE** `GA_PICKUP_MAX_POLL_SECS` — internal retry timing. Hardcode 30.
- **REMOVE** `GA_MEMORY_WAIT_SECS` — internal retry timing. Hardcode 60.
- **REMOVE** `KC_GATEWAY_TOKEN_TTL` — KiroCrew gateway token TTL; 24h is correct for everyone. Hardcode.
- **REMOVE** `GA_ENFORCE_HTTPS_REDIRECT` — staged rollout flag; Caddy owns HTTP→HTTPS redirects now. Remove.
- **REMOVE** `GA_CSP_ENFORCE` — staged rollout flag; turn CSP on fully and remove the toggle.
- **RESTRUCTURE** `ghostship.conf.example` — split into **Common** and **Advanced** sections so new users see ~10 relevant vars first, not ~50.
- **DOCS** — document the full model precedence chain: `dispatch(model=...)` > `KC_MODEL_OVERRIDE` > per-agent > `KC_MODEL_DEFAULT` > KiroCrew built-in.

**BREAKING**: `GA_PORTAL_PORT` renamed to `PORT`. Install.sh should warn and migrate automatically if `GA_PORTAL_PORT` is found in a user config file.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `config-file`: Remove vars no longer user-configurable (`HOST`, `GA_PORTAL_ADMIN_URL`, `GA_FILE_TTL_SECS`, `GA_PICKUP_MAX_POLL_SECS`, `GA_MEMORY_WAIT_SECS`, `KC_GATEWAY_TOKEN_TTL`, `GA_ENFORCE_HTTPS_REDIRECT`, `GA_CSP_ENFORCE`) from the supported variable list and the config-file spec scenario; note that `GA_PORTAL_PORT` is superseded by `PORT`.

## Impact

- `scripts/install.sh` — remove 8 var declarations from the built-in defaults block; rename `GA_PORTAL_PORT` to `PORT` throughout; hardcode removed values at their current defaults; warn + auto-migrate `GA_PORTAL_PORT` if found in user config; turn CSP enforcement on unconditionally.
- `transport/config.py` and `transport/server.py` — remove `GA_PORTAL_ADMIN_URL`, `GA_FILE_TTL_SECS`, `GA_PICKUP_MAX_POLL_SECS`, `GA_MEMORY_WAIT_SECS`, `KC_GATEWAY_TOKEN_TTL`, `GA_ENFORCE_HTTPS_REDIRECT`, `GA_CSP_ENFORCE` fields; hardcode their values.
- `config/ghostship.conf.example` — restructure into Common / Advanced sections; reflect all removals and rename.
- `docs/configuration.md` — reflect removals, rename, add model precedence table.
- `CHANGELOG.md` — breaking change entry for `GA_PORTAL_PORT` → `PORT`.
