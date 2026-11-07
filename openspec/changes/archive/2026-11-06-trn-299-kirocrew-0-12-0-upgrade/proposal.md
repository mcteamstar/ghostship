# Proposal

## Why

KiroCrew v0.12.0 was released on 2026-11-05, bringing kiro-cli 3.0.0 (a major version jump from
2.36.0), security hardening for cron governance and deny rules, and Bot/worktree isolation
improvements. Ghostship's base crew image is pinned to v0.11.2; upgrading keeps crews on a
supported gateway with the latest security fixes and kiro-cli runtime.

## What Changes

- Advance the `KC_BASE_IMAGE` pin from v0.11.2 → v0.12.0 in `crews/_base/admission/Containerfile`
  and `transport/config.py` (two occurrences).
- Re-verify the kiro-cli DB migration seed in `crews/_base/graduation/seed_kiro_db.py` against
  the v0.12.0 image. kiro-cli 3.0.0 is a major version bump — schema `(6, 5)` must be confirmed
  or updated before the image is released (this is the critical release gate).
- Update the annotation comment in `crews/_base/graduation/Containerfile`.
- Update `docs/configuration.md` KC_BASE_IMAGE digest reference.
- Bump `VERSION` to `0.12.0` and add a `CHANGELOG.md` entry.
- Deploy to corsair (dev), run e2e, then deploy to carrier.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `crew-image-build`: the two requirements naming v0.11.2 explicitly (image pin and DB seed
  annotation) must be updated to v0.12.0.

## Impact

- `crews/_base/admission/Containerfile` — KC_BASE_IMAGE default
- `transport/config.py` — kc_base_image string default (×2)
- `crews/_base/graduation/seed_kiro_db.py` — migration schema annotation (and possibly seed
  rows if schema changed)
- `crews/_base/graduation/Containerfile` — version comment
- `docs/configuration.md` — KC_BASE_IMAGE digest in env var table
- `VERSION`, `CHANGELOG.md`
- `openspec/specs/crew-image-build/spec.md` — delta updates two requirements
