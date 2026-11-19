# Proposal

## Why

The rate-limiting spec documents an obsolete `GA_TRUSTED_PROXY` switch and last-hop parsing, while code uses CIDR-based peer trust and the first forwarded hop. Operators and implementers therefore receive conflicting security guidance.

## What Changes

- Align the rate-limiting spec with `GA_TRUSTED_PROXY_CIDR` and the implemented peer-check and first-hop rules.
- Correct configuration documentation and examples, including the unset behavior and spoofing implications.
- Keep this change contract-and-documentation focused; do not change runtime behavior without a separately reviewed design.

## Capabilities

### New Capabilities

### Modified Capabilities

- `installation`: document the trusted-proxy CIDR configuration contract for operators.
- `rate-limiting`: specify the trusted-proxy condition and client-address derivation accurately.

## Impact

`openspec/specs/installation/spec.md`, `openspec/specs/rate-limiting/spec.md`, `docs/configuration.md`, and focused rate-limit tests. Runtime code is not expected to change.
