## Why

Raven's recurring check-in currently infers whether a worker persona is already in flight by reading the `agent` field on `/api/spawn` responses, but KiroCrew populates that field asynchronously after dispatch. When multiple Raven ticks fire in close succession (e.g. immediately after a long Ghost run), each can see an empty `agent` field and conclude no worker is in flight — dispatching duplicate Banshees (or Ghosts, or Reapers) into the subagent pool.

## What Changes

- Raven writes a dispatch-intent record to `raven@localhost` **before** calling `/api/spawn`, making the mailbox the durable intent point for each SDD transition. Because the gateway assigns the real task ID inside the spawn call, the pre-spawn record uses a unique local intent token; a post-spawn confirmation records the returned task ID. Subsequent Raven ticks check their own mailbox first; a pending or confirmed dispatch-intent causes them to hold until it is stale.
- Raven includes the intent token in a stable task-description marker, cross-checks the spawn list by that task text (not the `agent` field), and checks the `agent` field as a tertiary confirmation. All three layers must report clear before a new dispatch proceeds; a post-write election lets the oldest pending marker win if check-ins overlap.
- The `sdd` template standing-order instructions are updated to describe the token/assigned-ID handoff, layered checks, and pending-marker election so future Raven sessions apply the pattern consistently.
- The approach applies to all SDD transitions: Ghost dispatch, Banshee dispatch, and Reaper dispatch.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `autonomous-orchestration`: add requirement that Raven uses a layered signal approach (mailbox → stable task-description marker → agent field) before dispatching any worker persona, writes a tokenized dispatch-intent mail to `raven@localhost` before each spawn call, records the gateway-assigned task ID afterward, and elects one pending marker when check-ins overlap.
- `mail`: add requirement for a Raven self-coordination mail convention — tokenized pre-spawn dispatch-intents written to `raven@localhost`, followed by confirmations containing the server-assigned task ID, with subjects that subsequent Raven ticks can scan.

## Impact

- `academy/orders/sdd.md` — standing order template updated with layered dispatch-check instructions
- `academy/steering/STANDING_ORDERS.md` — may need cross-reference to the coordination pattern
- No transport changes required — this is entirely within Raven's prompt/instructions
