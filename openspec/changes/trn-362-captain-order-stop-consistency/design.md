# Design

## Context

See proposal.md for motivation. Check-ins and order changes already share a per-crew lock, while stop currently disables the schedule without taking it. Order creation currently writes an enabled schedule before appending mailbox content and logs/continues when the registry write fails.

## Goals / Non-Goals

**Goals:**
- Make stop a synchronization boundary for check-in dispatch.
- Prevent an order from being reported successful unless its mailbox write and enabled schedule persistence both succeed.
- Leave partial failures in a non-dispatching, diagnosable state.

**Non-Goals:**
- Cancel Raven work that the gateway has already accepted.
- Provide a distributed transaction across the registry file and the crew mailbox.
- Redesign mailbox storage or Captain scheduling.

## Decisions

- Use the existing per-crew Captain order lock for stop as well as check-in and order transitions. Stop waits for an in-flight check-in to release the lock, then disables the schedule before returning; subsequent check-ins acquire the lock and observe the disabled entry.
- Persist a candidate schedule in the disabled state first. If that registry write fails, return an error without appending the order, leaving the previous persisted state untouched.
- Append the standing instruction only after the disabled schedule is durable. If mailbox delivery fails, keep the schedule disabled and return an error.
- Enable the schedule only after mailbox delivery succeeds. If activation fails, attempt to persist the disabled state again and return an error. If that compensation also fails, return an explicit partial-state error and log enough context for operator reconciliation; never return `status: ordered` on this path.
- Alternative considered: append the mailbox instruction before changing the schedule. Rejected because a later registry failure could leave an active old schedule able to consume a new instruction even though the order call failed.

## Risks / Trade-offs

- [A failure after mailbox delivery can leave an unapplied instruction in the mailbox] → Keep the schedule disabled, return an error describing partial persistence, and require a later successful order or operator reconciliation before dispatch resumes.
- [Stop waits for an in-flight check-in] → This gives stop a clear completion boundary; already accepted Raven work is not cancelled.
- [Registry storage may remain unavailable during compensation] → Report the partial state and do not claim success; tests cover recoverable one-shot write failures and compensation behavior.

## Migration Plan

No data migration is required. Existing enabled schedules continue as stored. During an order update, the per-crew transition is serialized and uses a temporary disabled state. Rollback is reverting the Captain transition logic; any disabled entry from an interrupted order can be resumed by a successful order operation.
