# Proposal

## Why

The current OpenSpec v2 strict validation run reports 58 failures and 182 warnings, including 171 overlong requirements, placeholder Purpose sections, RFC wording, and unsupported `ticket` metadata. The repository needs a measured cleanup plan and a consistent way to keep Plane linkage while producing a clean validation baseline.

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
