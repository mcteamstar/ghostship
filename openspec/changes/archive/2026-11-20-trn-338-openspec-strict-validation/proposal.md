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

## Final Validation

Validation on 2026-11-20 used `openspec validate --all --strict --report full --json --store repo`. The repository has 87 validated items: 85 passed and 2 are warning-only failures. Both remaining warnings are overlong requirements; there are no Purpose placeholders, missing SHALL/MUST keywords, unsupported metadata keys, or other findings.

| Category | Baseline | Final |
|---|---:|---:|
| Overlong requirements | 168 | 2 |
| Placeholder Purpose sections | 2 | 0 |
| Missing SHALL/MUST | 5 | 0 |
| Unsupported `ticket` metadata | 3 | 0 |
| Total warnings | 178 | 2 |
| Items passed / failed | 29 / 58 | 85 / 2 |

Scenario review found no removed or changed original scenario behavior in the behavior-preserving edits. In `captain/independent-review`, duplicate stale four/five-report labels were consolidated and corrected to distinguish five review tracks from seven dispatched tasks. Its three test-coverage shards remain fixed as in the source order; configurability is deferred to TRN-344. No order or runtime behavior changed.

### Intentional Remaining Exceptions

- `transport/crews-rest-api` retains one overlong requirement because its complete typed response schema is the public API contract.
- `yaml-config` retains one overlong requirement because its old-to-new path table is the exhaustive compatibility mapping, not a set of optional examples.

Both remaining strict findings are accounted for above.

### Independent Review Corrections

Review against source found that wording cleanup had dropped type and nullability details from the `crews()` response contract and the floating-point type of `RateLimiter.window_secs`; those contracts are restored. The dashboard specifications also still described removed transport-side listeners and the removed `GA_DASHBOARD_PORT_ENABLED` switch, so they now describe Portal-managed ports and transport proxying. These are specification corrections only; no runtime behavior changed.
