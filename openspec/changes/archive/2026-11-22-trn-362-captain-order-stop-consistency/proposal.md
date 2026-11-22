# Proposal

## Why

Captain check-ins and stop operations can race because stop does not share the per-crew order lock used by check-ins. Separately, ordering can continue after schedule persistence fails, and an order-mail failure can leave an enabled schedule without its corresponding instruction. These paths can report or leave a Captain state that does not match the persisted schedule and mailbox.

## What Changes

- Serialize stop with check-in and order transitions so that after stop returns no new check-in dispatch begins; a check-in already in progress may finish before stop returns.
- Make order persistence failure-safe: report `ordered` only after schedule and standing instruction are aligned, and leave the schedule disabled if a partial update cannot be completed.
- Add deterministic coverage for stop/check-in races and injected schedule or mailbox write failures.

## Capabilities

- `captain`
- `testing/captain`

## Impact

Captain order/stop coordination, registry and mailbox failure handling, and focused unit tests change. This does not cancel Raven work already accepted by the gateway.
