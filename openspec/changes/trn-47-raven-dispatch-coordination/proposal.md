## Why

Raven's recurring check-in currently infers whether a worker persona is already in flight by reading the `agent` field on `/api/spawn` responses, but KiroCrew populates that field asynchronously after dispatch. When multiple Raven ticks fire in close succession (e.g. immediately after a long Ghost run), each can see an empty `agent` field and conclude no worker is in flight — dispatching duplicate Banshees (or Ghosts, or Reapers) into the subagent pool.

## What Changes

- Raven writes a dispatch-intent record to `raven@localhost` **before** calling `/api/spawn`, making the mailbox the atomic commit point for each SDD transition. Subsequent Raven ticks check their own mailbox first; a pending or recent dispatch-intent record causes them to hold.
- Raven also cross-checks the spawn list by task **description** (not `agent` field) and checks `agent` field as a tertiary confirmation. All three layers must report clear before a new dispatch proceeds.
- The `sdd` template standing-order instructions are updated to describe this layered check pattern so future Raven sessions apply it consistently.
- The approach applies to all SDD transitions: Ghost dispatch, Banshee dispatch, and Reaper dispatch.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `autonomous-orchestration`: add requirement that Raven uses a layered signal approach (mailbox → task description → agent field) before dispatching any worker persona, and writes a dispatch-intent mail to `raven@localhost` before each spawn call to provide an atomic coordination signal across concurrent check-ins.
- `mail`: add requirement for a Raven self-coordination mail convention — dispatch-intent messages written to `raven@localhost` before persona dispatch, with a defined subject format (`dispatching <persona> <task_id>`) that subsequent Raven ticks can scan.

## Impact

- `academy/orders/sdd.md` — standing order template updated with layered dispatch-check instructions
- `academy/steering/STANDING_ORDERS.md` — may need cross-reference to the coordination pattern
- No transport changes required — this is entirely within Raven's prompt/instructions
