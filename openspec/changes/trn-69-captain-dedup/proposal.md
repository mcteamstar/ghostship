## Why

When Raven runs a captain check-in cycle, two concurrent or overlapping check-in
instances can each observe an empty `kirocrew spawn list` and both proceed to
dispatch the same persona task for the same SDD transition. The result is
duplicate dispatches that waste compute, race on shared state (two tasks checking
off the same `tasks.md` items or advancing the same OpenSpec artifact), and
require manual cancellation. A single lifecycle transition must produce exactly
one dispatch, even under overlapping check-ins.

## What Changes

- Introduce a **layered 3-signal dispatch-coordination protocol** that Raven MUST
  apply, in order, before every persona dispatch:
  1. **Mailbox intent signal (primary):** a pending or confirmed dispatch-intent
     message in `raven@localhost` for the target persona blocks re-dispatch.
  2. **Task-description marker signal (secondary):** an in-flight `spawn list`
     task whose `task` description begins with the stable marker
     `SDD dispatch <change> <persona> <intent_id>` blocks re-dispatch.
  3. **Agent-field signal (tertiary):** the asynchronous `agent` field in
     `spawn list` is a final confirmation only, never the sole guard.
- Define a **pending-marker election**: after writing its pending intent, a
  check-in re-scans the mailbox and yields to any older unconfirmed pending marker
  for the same persona, so overlapping check-ins cannot both spawn.
- Define **intent lifecycle and staleness**: `intent-<uuid>` tokens, pending →
  confirmed transition keyed on the gateway-assigned spawn task ID, and the exact
  conditions under which a pending or confirmed intent becomes stale and stops
  blocking.
- Document the protocol authoritatively in the SDD order and reference it from the
  `## Avoid duplicate dispatches` section of the crew standing orders.
- Add validation / test steps that exercise the overlapping-check-in race.

## Capabilities

### New Capabilities
- `crew-orchestration/dispatch-coordination`: the rules a dispatching agent
  (Raven) must follow to guarantee at-most-one dispatch per lifecycle transition —
  the 3-signal pre-dispatch check, the intent-marker mailbox protocol, the
  pending-marker election, and intent staleness semantics.

### Modified Capabilities
<!-- None: no existing spec under openspec/specs/ describes dispatch behavior yet. -->

## Impact

- **Standing orders / prompts:** `academy/orders/sdd.md` (authoritative protocol
  text) and the `## Avoid duplicate dispatches` section of `STANDING_ORDERS.md`
  (cross-reference).
- **Crew runtime:** the mailbox (Maildir under `/var/mail/`) is the coordination
  substrate; `kirocrew spawn list` supplies the task-description and agent-field
  signals; `/api/spawn` returns the confirming task ID. No new services are
  required — the protocol is layered on existing primitives.
- **Behavior:** a lifecycle transition produces exactly one dispatch even when
  check-ins overlap; a losing check-in holds and reassesses on the next cycle.
