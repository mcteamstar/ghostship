## Context

Academy assets are loaded in `_copy_agents`, `_load_crew_manifest`, and `_load_order_template` with best-effort, warn-and-continue semantics. Misconfigured assets fail silently at launch time. See proposal.md for the problem statement.

## Goals / Non-Goals

**Goals:** Surface misconfiguration as startup warnings before any crew is launched. Add unit tests for validation logic.

**Non-Goals:** Make validation fatal (operators may intentionally have partial academies during development). Validate skill or steering file content beyond existence. Address TRN-71 modularisation.

## Decisions

### Startup-time, not launch-time

**Decision:** Run `_validate_academy()` once at transport startup, not on every `launch` call.

Startup validation catches misconfiguration at deploy time. Per-launch validation would add latency to every `launch` and produce repeated warnings for the same misconfiguration. The academy contents are snapshotted at install time and don't change at runtime.

### Warnings, not errors

**Decision:** Log `WARNING`-level entries for each validation failure; do not raise or halt startup.

Operators may be mid-customisation with a partially valid academy. A fatal validation would block the transport from starting entirely, which is worse than a warning. The goal is visibility, not enforcement.

### Validation scope

Three checks:
1. **Agent JSON schema** — every `*.json` in `/agents` parses and has `name`, `description`, `tools` fields (all required by KiroCrew)
2. **Manifest cross-reference** — every name in a manifest's `agents`/`skills`/`steering` arrays exists in the corresponding pool (skip `"*"` manifests)
3. **Order template front-matter** — every `*.md` in `/orders` has parseable YAML front-matter and at least one `{{...}}` placeholder

**Decision:** Skip content validation of skills and steering docs — these are freeform Markdown and have no required schema.

### Implementation location

New `_validate_academy()` function in `server.py`, called in the startup sequence alongside `_reconcile_registry()`. Returns a list of warning strings; the caller logs each one.

## Risks / Trade-offs

- Validation runs at startup only — a file changed after startup is not re-validated until next restart. Acceptable given the snapshotted-at-install model.
- `_validate_academy()` path depends on the mounted academy paths (`/agents`, `/orders`). These are well-established constants; no risk of drift.

## Migration Plan

No migration. Operators with valid academies see no change. Operators with misconfigured academies see new startup warnings they can act on.
