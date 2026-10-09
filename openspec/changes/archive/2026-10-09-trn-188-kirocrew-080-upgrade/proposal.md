# TRN-188: Upgrade Ghostship to KiroCrew 0.8.0

## Why

KiroCrew 0.8.0 stable is imminent. Ghostship `release/0.6.0` is currently
developed against `0.8.0-insider.8` (the last insider build before the stable
release) but has not been released to academy yet. The branch cannot ship until
we confirm full compatibility with 0.8.0 stable — or adapt to any breaking
changes it introduces.

This is a research-first pylon. We need to diff insider.8 against the stable
0.8.0 release, validate the attestation fixes (TRN-185/186/187) hold, verify
`seed_kiro_db.py` migration counts, and confirm no new breaking changes affect
the Ghostship feature surface.

## What Changes

- **Bump `KC_BASE_IMAGE`** from `0.8.0-insider.8` to `0.8.0` once stable is
  released and validated
- **Verify or update `seed_kiro_db.py`** — migration count may change between
  insider.8 and stable
- **Validate TRN-186/187 fixes** — member enrollment and attestation must work
  on 0.8.0 stable (they were developed against insider.8)
- **Investigate any new breaking changes** in the 0.8.0 CHANGELOG vs insider.8
- **Ship `release/0.6.0`** to academy once validation passes

## What does NOT change (unless research reveals otherwise)

- The member enrollment approach (`POST /api/members/{slug}/thread`)
- The attestation fix (`X-Session-Key` in spawn calls)
- The `_resolve_dispatch_slot` / `enrolled_agents` architecture
- Order templates and Raven agent spec

## Capabilities

### Modified Capabilities
- `crew-lifecycle` — `KC_BASE_IMAGE` version bump
- `crew-member-enrollment` — re-validate against 0.8.0 stable

## Impact

- `crews/_base/admission/Containerfile` — `KC_BASE_IMAGE` arg
- `transport/config.py` — `kc_base_image` default
- `config/ghostship.conf.example` — `KC_BASE_IMAGE`
- `crews/_base/container_scripts/seed_kiro_db.py` — migration count
- `tests/unit/test_config_from_env.py` — version assertion
- `terran/hyperv/academy/ghostship.conf` — `KC_BASE_IMAGE`
