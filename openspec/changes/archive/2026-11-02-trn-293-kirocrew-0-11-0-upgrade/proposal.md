# Proposal

## Why

The Ghostship spec-ops crew image is pinned to KiroCrew v0.10.0 (released ~Aug 2026).
KiroCrew v0.11.1 (released 2026-10-31) ships two fixes that directly affect Ghostship
in production: a memory WAL race fix critical for 7-concurrent-agent independent-review
runs, and a shell reader security fix that closes a `-c`-after-options bypass in the
deny-list enforcement that all non-Wraith personas rely on. Three CVEs (filelock, undici,
zod) are also resolved. The upgrade is low-risk — kiro-cli remains the dispatch engine
and no config changes are required.

## What Changes

- Bump `KC_BASE_IMAGE` in `crews/_base/admission/Containerfile` from the v0.10.0 digest
  to the v0.11.1 multi-arch index digest
- Re-verify `seed_kiro_db.py` migration count and schema against the v0.11.1 image
  (blocking: if the kiro-cli SQLite migration schema changed, the seed script must be
  updated before the image can be built)
- Update the `KC_BASE_IMAGE` comment block with the new version and digest
- Rebuild and test the `spec-ops` crew image on corsair and carrier
- Document the `--no-kas` install flag for operators who do not want the KAS binary
  downloaded during fresh installs (KAS is the new upstream default but Ghostship
  continues to use kiro-cli via `GA_CREW_AGENT`)

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `crew-image-build`: KC_BASE_IMAGE must be pinned to v0.11.1+ and the
  `seed_kiro_db.py` migration seed must match the version's kiro-cli SQLite schema

## Impact

- `crews/_base/admission/Containerfile` — `KC_BASE_IMAGE` arg and comment
- `crews/_base/graduation/seed_kiro_db.py` — possibly updated migration rows if schema
  changed (must be verified against v0.11.1 image)
- `release/0.11.0` branch — all crew image changes land here
- Corsair and carrier spec-ops images rebuilt and redeployed
- No changes to transport, academy, agents, steering, orders, or install scripts
- KAS engine: not adopted in this TRN; separate future change
