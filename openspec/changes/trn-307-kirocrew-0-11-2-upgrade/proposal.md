# Proposal

## Why

KiroCrew v0.11.2 is a hotfix over v0.11.1 (released 2026-11-04), fixing KAS engine MCP
server startup, crewmate broker overlay routing, and MCP settings file corruption on parse
errors. The changes are low-risk — kiro-cli remains the dispatch engine and no config
changes are required. As a hotfix release it should land quickly.

## What Changes

- Obtain the v0.11.2 multi-arch index digest via `podman manifest inspect ghcr.io/kirodotdev/kirocrew:v0.11.2`
- Bump `KC_BASE_IMAGE` in `crews/_base/admission/Containerfile` from the v0.11.1 digest
  to the v0.11.2 digest
- Re-verify `seed_kiro_db.py` migration count and schema against the v0.11.2 image
  (the release notes do not indicate any kiro-cli SQLite schema changes, but this must
  be confirmed before building)
- Update the `KC_BASE_IMAGE` comment block with the new version, digest, and date
- Update `transport/config.py` comment referencing v0.11.1 → v0.11.2
- Update `openspec/specs/crew-image-build/spec.md` to reflect the new pin
- Rebuild and smoke-test the `spec-ops` image on the deployment host

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `crew-image-build`: KC_BASE_IMAGE pin advances to v0.11.2; `seed_kiro_db.py`
  migration annotation updated (or unchanged if schema is identical)

## Impact

- `crews/_base/admission/Containerfile` — `KC_BASE_IMAGE` arg and comment
- `crews/_base/graduation/seed_kiro_db.py` — migration annotation comment (schema
  likely unchanged from v0.11.1; must verify)
- `transport/config.py` — version comment
- `openspec/specs/crew-image-build/spec.md` — pin requirement updated
- Corsair spec-ops image rebuilt; carrier rebuilt on next `ghostship upgrade`
- No changes to transport, academy, agents, steering, orders, or install scripts
