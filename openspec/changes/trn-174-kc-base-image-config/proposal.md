## Why

The KiroCrew base image version string is hardcoded as a module-level constant in both `transport/lifecycle.py` and `transport/server.py`, contrary to the spec (`openspec/specs/crew-lifecycle/spec.md` L663) which states it SHALL appear in exactly two places in `transport/config.py` and nowhere else. This means every base-image version bump requires edits in at least two Python files beyond `config.py`, and missing one causes a version mismatch where the ephemeral login container uses a different image than the crew container.

## What Changes

- Add `kc_base_image: str` field to the `Config` dataclass in `transport/config.py`, reading the `KC_BASE_IMAGE` env var with `"ghcr.io/kirodotdev/kirocrew:0.6.0"` as the default
- Remove the module-level `KC_BASE_IMAGE` constant from `transport/lifecycle.py` (L200); replace all usages with `cfg.kc_base_image`
- Remove the module-level `KC_BASE_IMAGE` constant from `transport/server.py` (L396); replace all usages with `cfg.kc_base_image`
- Update unit tests that currently patch `lifecycle.KC_BASE_IMAGE` or `server.KC_BASE_IMAGE` to patch `config.Config.kc_base_image` instead

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

_(none — the spec already requires this; this change brings the implementation into compliance. No externally observable behaviour changes.)_

## Impact

- `transport/config.py` — add `kc_base_image` field and `from_env()` mapping
- `transport/lifecycle.py` — remove module-level constant, thread `cfg.kc_base_image` through callers
- `transport/server.py` — remove module-level constant, use `cfg.kc_base_image`
- `tests/unit/` — update mock patch targets from `lifecycle.KC_BASE_IMAGE` / `server.KC_BASE_IMAGE` to `config`-level
- Future version bumps: single change to default value in `config.py` (plus `admission/Containerfile FROM`)
- `KC_BASE_IMAGE` env var is now supported as an override (operators can pin a custom image without rebuilding)
