# Proposal

## Why

The OpenSpec v2 strict validation baseline was refreshed on 2026-11-20 with `openspec validate --all --strict --report findings --json`. It covers 87 items: 58 failed (55 specs and 3 active changes) and 29 passed. The 178 warnings comprise 168 overlong requirements, 2 placeholder Purpose sections, 5 requirements missing SHALL/MUST wording, and 3 unsupported `ticket` metadata keys. All findings are warnings; there are no error-level findings. The repository needs a measured cleanup plan and a consistent way to keep Plane linkage while producing a clean validation baseline.

## What Changes

- Record a reproducible strict-validation baseline and group findings by cause.
- Define repository-level expectations for OpenSpec v2 artifact validity and ticket metadata.
- Resolve findings in manageable batches, preserving requirement meaning and Plane pylon traceability.
- Re-run strict validation and record the remaining baseline or zero-finding result.

## Capabilities

### New Capabilities

- `trn-openspec-validation`: repository requirements for valid, maintainable OpenSpec artifacts and traceable change metadata.

### Modified Capabilities

## Impact

OpenSpec specs, change metadata and artifacts, project workflow guidance, and validation commands. No runtime service behavior changes.
