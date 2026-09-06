## Why

KiroCrew 0.5.0 was released 2026-08-29. Ghostship currently pins `ghcr.io/kirodotdev/kirocrew:0.4.0`
as both the crew base image (`crews/_base/admission/Containerfile`) and the ephemeral login-container
(`KC_BASE_IMAGE` in `config/ghostship.conf.example`). Staying on 0.4.0 means ghostship misses
hardened security-policy validation, a stricter agent-spec reader, and improved MCP isolation,
and it accumulates an increasing delta against upstream that gets harder to close over time.

The full analysis is in `docs/kirocrew-v0.5.0-migration.md`. Bottom line: none of 0.5.0's ten
breaking changes touch a code path ghostship actively uses — no dictation, no snapshot-to-S3, no
Knowledge page, no Auto-Triage. The upgrade is **small-to-medium**: the image pin bump is trivial;
the real effort concentrates in (1) re-verifying the pre-seeded kiro-cli migration DB (the single
highest-risk item) and (2) validating three stricter 0.5.0 behaviours before rebuilding.

## What Changes

- **Bump crew base image**: `crews/_base/admission/Containerfile` `FROM ghcr.io/kirodotdev/kirocrew:0.4.0` → `0.5.0` and accompanying comment.
- **Bump login-container image**: `KC_BASE_IMAGE` in `config/ghostship.conf.example` `0.4.0` → `0.5.0`.
- **Re-verify pre-seeded DB**: `crews/_base/graduation/seed_kiro_db.py` and its `Containerfile` preamble — confirm or update migration row count/schema against the 0.5.0 image's kiro-cli. This is the only item that can cause a "looks fine" bump to break silently in production.
- **Refresh stale version strings**: four files carry human-readable `0.4.0` references that should track the current pin (`scripts/uninstall.sh`, `academy/mcp/README.md`, the `GA_CREW_AGENT` comment in `config/ghostship.conf.example`, and `CHANGELOG.md`).
- **Validate governance policy**: 0.5.0 hard-fails on a misspelled `sandbox` key or malformed `publish` section (was silently ignored in 0.4.0). The three templates in `academy/policies/` need a read-and-confirm pass.
- **Validate agent specs**: 0.5.0 refuses (rather than skipping) malformed agent specs. The six files in `academy/agents/` need a well-formedness check.
- **Validate MCP pooling**: the `poolable: false` auto-injection in `transport/lifecycle.py` was written for 0.4.0 semantics; confirm it still behaves correctly under 0.5.0's per-connection isolation model for `headers`-bearing servers.
- **Rebuild and full test pass**: rebuild the image stack via `scripts/install.sh`, run `tests/run.sh`, and smoke-test a live crew end-to-end.

## Capabilities

### New Capabilities

_(none — this is a dependency upgrade, not a feature change)_

### Modified Capabilities

- `crew-lifecycle`: base image version moves to 0.5.0; kiro-cli pre-seed may gain new migration rows.
- `crew-governance`: policy injection validated against 0.5.0's stricter `security_policy.json` validator.
- `mcp-server-config`: `poolable: false` auto-injection re-confirmed under 0.5.0 MCP isolation semantics.

## Non-Goals

- Adopting 0.5.0's centrally-published `security_policy.json` fleet feature. Ghostship's per-crew injected policy is correct today; fleet policy is a separate design change.
- Adopting `session_send`, the conductor agent, or other new orchestration primitives from 0.5.0.
- Bumping Node.js or `@fission-ai/openspec` in `crews/spec-ops/Containerfile` — those are independent pins; not in scope here.

## Risk

The one non-obvious risk is the pre-seeded kiro-cli DB. If 0.5.0's kiro-cli added migration rows
and `seed_kiro_db.py` is not updated, crews start with an under-migrated DB and may fail silently
or misbehave. The mitigation is Step 1 of the tasks — it must run before any pin change is committed.

All other validation steps (policy, agent specs, MCP pooling) are low-effort confirms; the only
expected edit is if the DB schema changed.

## Impact

- `crews/_base/admission/Containerfile` — one-line `FROM` bump + comment.
- `crews/_base/graduation/seed_kiro_db.py` — possible new `INSERT INTO migrations` rows and/or schema `CREATE TABLE`/`CREATE INDEX` additions; version banner update.
- `crews/_base/graduation/Containerfile` — version banner in the `FRAGILITY WARNING` comment block.
- `config/ghostship.conf.example` — `KC_BASE_IMAGE` bump; `GA_CREW_AGENT` comment refresh.
- `scripts/uninstall.sh` — one human-readable version string.
- `academy/mcp/README.md` — one version reference in the `poolable: false` explanation.
- `CHANGELOG.md` — new entry for the 0.5.0 bump.
- `academy/policies/{default,strict,research}.json` — read-only confirm; edit only if a key is misspelled.
- `academy/agents/{ghost,spectre,banshee,wraith,reaper,raven}.json` — read-only confirm; edit only if malformed.
