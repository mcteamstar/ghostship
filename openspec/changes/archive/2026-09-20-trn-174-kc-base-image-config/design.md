## Context

See proposal.md. `KC_BASE_IMAGE` is currently a module-level constant duplicated in `transport/lifecycle.py` (L200) and `transport/server.py` (L396). The spec requires it to live exclusively in `transport/config.py` as `cfg.kc_base_image`. `config.py` has no such field today.

The string `"ghcr.io/kirodotdev/kirocrew:0.6.0"` is used in:
- `lifecycle.py`: as the image for ephemeral login containers (`_start_login_container`, `_start_claude_login_container`, `_start_codex_login_container`)
- `server.py`: as the image referenced in the `kc_base_image` resource response

## Goals / Non-Goals

**Goals:**
- Consolidate `KC_BASE_IMAGE` into `config.py` as `kc_base_image`, readable via env var
- Remove the duplicate module-level constants from `lifecycle.py` and `server.py`
- Update test patches to target the config level

**Non-Goals:**
- Changing the default value (`0.6.0` stays)
- Syncing `admission/Containerfile FROM` automatically (it remains a manual step)
- Making `seed_kiro_db.py` read the config value (build-time artefact, addressed by TRN-173)

## Decisions

**Add as a `Config` dataclass field with env-var override.** Pattern matches every other configurable value in the codebase. Field name: `kc_base_image` (snake_case, consistent with `kc_image` already in `Config`). Env var: `KC_BASE_IMAGE` (already used as the constant name, no rename needed). Default: `"ghcr.io/kirodotdev/kirocrew:0.6.0"`.

**Thread `cfg` into callers via the existing `cfg` module global.** `lifecycle.py` and `server.py` both import and bind `cfg` at module init. Replacing `KC_BASE_IMAGE` with `cfg.kc_base_image` at the existing call sites is the minimal change. No new function signatures needed.

**Update test patches.** Tests that currently do `@patch("transport.lifecycle.KC_BASE_IMAGE", "fake:0.0")` must instead patch `transport.config.cfg.kc_base_image` or use `Config(kc_base_image="fake:0.0")` in the test setup. Check for all patch sites before making changes.

## Risks / Trade-offs

- [`KC_BASE_IMAGE` env var now respected at runtime] Previously ignored (constant). An operator who sets `KC_BASE_IMAGE` in their environment will now have it take effect — this is the correct behaviour and is documented in `ghostship.conf.example`. No deployment currently relies on the constant being immune to env override; the env var was never surfaced before.
- [Test patch sites] Several tests likely patch the module-level constant directly. Missing a patch site would cause tests to use the real image string rather than the test value. Mitigation: grep for all `KC_BASE_IMAGE` patch targets before writing the implementation.
