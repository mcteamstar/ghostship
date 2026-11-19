# Proposal

## Why

Privacy scanning is intended to be one reviewer shard within Indy, not a standalone Captain workflow. Removing the separate order avoids advertising a one-shot workflow that duplicates the privacy review already performed by independent-review.

## What Changes

- Remove the standalone `privacy` Captain order and its `privacy-probe` and `scrub` aliases.
- Keep the privacy review shard and consolidated Privacy section in the `independent-review` workflow unchanged.
- Remove the standalone order description from operator documentation and OpenSpec requirements.
- Verify the built-in order catalog no longer lists the removed names and Indy still includes privacy review.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `captain/privacy-probe`: Remove the standalone privacy Captain workflow requirements. Privacy scanning remains covered by `captain/independent-review`.

## Impact

Removes `academy/orders/privacy.md`; updates `README.md` and `docs/architecture.md`; updates Captain template tests and OpenSpec delta requirements. The Captain order catalog is dynamically loaded from Academy order files, so no transport implementation change is expected.
