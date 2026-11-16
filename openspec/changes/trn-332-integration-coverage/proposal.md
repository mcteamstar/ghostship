# Proposal

## Why

CI runs unit tests and six shell integration scripts, but the repository's Python integration suites are outside the standard runner. The Admiral signature verifier also lacks direct behavioral tests, leaving important release checks dependent on manual execution and static review.

## What Changes

- Add a supported runner/CI path for the Python integration suites, accounting for their runtime prerequisites.
- Add behavioral tests for valid signatures, tampered mail, and missing public keys in `verify-admiral-sig`.
- Define and add a practical automated install/start journey where CI can provide its prerequisites.
- Retain existing Maildir count coverage; it already exists in `tests/unit/test_captain.py`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `transport-test-coverage`: specify execution of the supported integration suites and direct signature-verifier behavior coverage.

## Impact

Test runner scripts, GitHub Actions workflows, integration and crew-image tests, and documentation of any prerequisite-backed test path. Runtime product behavior is unchanged.
