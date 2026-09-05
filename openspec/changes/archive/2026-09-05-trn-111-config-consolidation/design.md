## Context

See proposal.md for motivation. Current state:

- `transport/config.py` already reads `PORT` (line 183) as `cfg.port`, used as `PORT` in `server.py`. `GA_PORTAL_PORT` is a dead config field (read into `cfg.ga_portal_port` but never referenced in server.py or elsewhere).
- The 8 vars being removed (`HOST`, `GA_PORTAL_ADMIN_URL`, `GA_FILE_TTL_SECS`, `GA_PICKUP_MAX_POLL_SECS`, `GA_MEMORY_WAIT_SECS`, `KC_GATEWAY_TOKEN_TTL`, `GA_ENFORCE_HTTPS_REDIRECT`, `GA_CSP_ENFORCE`) are all still live in `config.py` and `server.py` as module-level constants, with hardcoded defaults.
- `install.sh` declares both `PORT=64057` (line 52) and `GA_PORTAL_PORT=64057` (line 93) in its built-in defaults block, and uses `GA_PORTAL_PORT` throughout the Caddy and compose templates.
- `config/ghostship.conf.example` is a flat list; `GA_PORTAL_PORT` appears as a commented-out var.

## Goals / Non-Goals

**Goals:**
- Remove 8 config vars from the operator-visible surface; hardcode their values
- Rename `GA_PORTAL_PORT` → `PORT` in `install.sh` (already done in Python)
- Auto-migrate `GA_PORTAL_PORT` in user config files with a warning
- Restructure `ghostship.conf.example` into Common / Advanced sections
- Document the model precedence chain in `docs/configuration.md`

**Non-Goals:**
- Changing any default values — every hardcoded value matches the existing default
- Removing `HOST` from the Python layer — it may still be useful for non-containerised installs; the proposal removes it from `install.sh`'s user-facing surface only
- Changing `KC_MODEL_OVERRIDE` or `KC_MODEL_DEFAULT` behaviour

## Decisions

### Decision 1: `ga_portal_port` config field removal is safe

`cfg.ga_portal_port` is a dead field — it's read from `GA_PORTAL_PORT` in `config.py` but never accessed in `server.py` or any other transport module. It can be removed entirely from the `Config` dataclass. `install.sh` is the only consumer that uses `GA_PORTAL_PORT`, and it'll be migrated to `PORT`.

### Decision 2: `HOST` removal scope

`HOST` is removed from `install.sh`'s defaults block and from `ghostship.conf.example`, but its Python handling in `config.py` stays — it's plausibly useful for non-containerised or custom installs. The operator-facing surface shrinks; the Python field remains as a no-doc escape hatch.

### Decision 3: Migration guard in install.sh

When `--config` is passed, `install.sh` checks if the config file contains `GA_PORTAL_PORT`. If found, it prints a warning and auto-substitutes `GA_PORTAL_PORT` with `PORT` before sourcing the file. This is a one-line sed+warning, not a full migration framework.

### Decision 4: `ghostship.conf.example` structure

Split into two sections:
- **Common** (~10 vars): `PORT`, `GA_HOST_URL`, `GA_API_KEY`, `KIRO_API_KEY`, `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE`, `KC_MODEL_OVERRIDE`, `KC_MODEL_DEFAULT`, `GA_GIT_AUTHOR_NAME`, `GA_GIT_AUTHOR_EMAIL`
- **Advanced** (everything else): lifecycle tuning, machine config, dashboard, TLS, security, model thresholds

### Decision 5: CSP enforcement unconditional

`GA_CSP_ENFORCE` is removed and CSP is turned on always. The `ga_csp_enforce` field is removed from `Config`; the relevant CSP header is emitted unconditionally. Any tests that branch on `GA_CSP_ENFORCE` need updating.

## Risks / Trade-offs

**Risk: Operators with `GA_PORTAL_PORT` in their config** → Mitigated by the auto-migration guard in install.sh. Anyone who set `GA_PORTAL_PORT` gets a warning and automatic substitution.

**Risk: `GA_MEMORY_WAIT_SECS` removal** → It was used by `_ensure_crew_running`'s memory wait loop. Hardcoding to 60 is safe — no one has a reason to change it.

**Risk: Unit tests referencing removed config vars** → `test_server.py` and `test_lifecycle.py` construct `Config` objects directly; any test that passes `ga_file_ttl_secs=`, `ga_csp_enforce=`, etc. will break after the field is removed. These must be caught and updated as part of the change.
