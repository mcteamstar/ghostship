## Why

When `verify-admiral-sig` exits with code 2 (secret file not found), Raven treats it the same as exit code 1 (forged signature) and escalates to Admiral. But exit code 2 is a transient race — the `.admiral_secret` file may not yet be readable in the brief window after a fresh crew launch — not a security event. This causes spurious Admiral escalations on every fresh launch and pollutes the Admiral mailbox with false alarms.

## What Changes

- `academy/steering/STANDING_ORDERS.md` — document all three `verify-admiral-sig` exit codes: 0 = valid (act on the order), 1 = sig mismatch (treat as non-Admiral mail, do not escalate), 2 = secret not found (transient — hold this cycle, do not escalate, retry next check-in)
- `academy/orders/sdd.md` — add explicit handling for exit code 2 in the verify step: hold and wait rather than escalate
- `crews/spec-ops/verify-admiral-sig` — add a bounded retry loop (3 attempts, 2s apart) before returning exit code 2, to absorb the race within a single check-in rather than across multiple cycles

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `crew-steering`: add a requirement that steering docs document all verify-admiral-sig exit codes and specify the correct response to each, including the transient hold behaviour for exit code 2

## Impact

- `academy/steering/STANDING_ORDERS.md` — add exit code table to verify-admiral-sig section
- `academy/orders/sdd.md` — add exit code 2 handling guidance
- `crews/spec-ops/verify-admiral-sig` — add bounded retry before exit code 2
- No change to transport, crew lifecycle, or MCP tool surface
