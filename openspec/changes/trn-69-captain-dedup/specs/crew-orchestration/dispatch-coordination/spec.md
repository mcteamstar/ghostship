## Purpose

Defines the coordination rules a dispatching agent (Raven) must follow so that a
single SDD lifecycle transition produces exactly one persona dispatch, even when
check-in cycles overlap.

## ADDED Requirements

### Requirement: Layered 3-signal pre-dispatch check

Before dispatching any persona for an SDD transition, the dispatching agent SHALL
evaluate three coordination signals, in order, and MUST NOT dispatch unless all
three are clear:

1. **Mailbox intent signal (primary):** the agent SHALL scan `raven@localhost` for
   an unconfirmed pending intent (`dispatching <persona> <intent_id>`) or a
   confirmed intent (`dispatching <persona> <spawn_task_id>`) for the target
   persona. A non-stale intent means the persona is already dispatched.
2. **Task-description marker signal (secondary):** the agent SHALL cross-check the
   `task` field in `kirocrew spawn list` for an in-flight task whose description
   begins with `SDD dispatch <change> <persona> <intent_id>`, matching change,
   persona, and intent token. The `agent` field MUST NOT be used for this check.
3. **Agent-field signal (tertiary):** the agent MAY check the `agent` field in
   `kirocrew spawn list` as a final confirmation only. Because it is populated
   asynchronously, it MUST NOT be the sole dispatch guard.

If any signal indicates an in-flight or recently dispatched task, the agent SHALL
hold and reassess on the next check-in rather than dispatch.

#### Scenario: All signals clear
- **WHEN** the mailbox has no non-stale intent, `spawn list` has no matching
  task-description marker, and the agent field shows no matching in-flight agent
- **THEN** the dispatching agent proceeds to the intent-marker dispatch protocol

#### Scenario: Mailbox intent blocks re-dispatch
- **WHEN** `raven@localhost` holds a non-stale pending or confirmed intent for the
  target persona
- **THEN** the dispatching agent holds and does not dispatch, and reassesses on
  the next check-in

#### Scenario: Task-description marker blocks re-dispatch
- **WHEN** `kirocrew spawn list` shows an in-flight task whose description begins
  with `SDD dispatch <change> <persona> <intent_id>` for the same change and persona
- **THEN** the dispatching agent holds and does not dispatch

#### Scenario: Agent field alone does not authorize a dispatch
- **WHEN** the agent field is empty but a non-stale mailbox intent or matching
  task-description marker exists
- **THEN** the dispatching agent holds; a clear agent field alone is insufficient
  to proceed

### Requirement: Intent-marker dispatch protocol

Once all three signals are clear and a transition requires a dispatch, the
dispatching agent SHALL generate a unique local `intent_id` of the form
`intent-<uuid>`, place it at the start of the worker task description as
`SDD dispatch <change> <persona> <intent_id>`, and write a pending dispatch-intent
message to `raven@localhost` (`To: raven@localhost`,
`From: raven+<raven_task_id>@localhost`, subject `dispatching <persona> <intent_id>`)
BEFORE calling `/api/spawn`. The agent MUST NOT invent or claim a spawn task ID
before the gateway assigns one inside `/api/spawn`.

After the spawn succeeds, the agent SHALL write a confirmation message with subject
`dispatching <persona> <spawn_task_id>` using the gateway-returned ID, including the
`intent_id` in the body to link the two records. If `/api/spawn` fails, the agent
SHALL write no confirmation.

#### Scenario: Pending marker precedes spawn
- **WHEN** the agent decides to dispatch a persona
- **THEN** it writes the pending intent message to `raven@localhost` before
  calling `/api/spawn`

#### Scenario: Confirmation follows a successful spawn
- **WHEN** `/api/spawn` returns a spawn task ID
- **THEN** the agent writes a confirmation message keyed on that ID and linking the
  originating `intent_id`

#### Scenario: Failed spawn writes no confirmation
- **WHEN** `/api/spawn` fails
- **THEN** the agent writes no confirmation message and leaves only the pending
  marker, which becomes stale by the staleness rules

### Requirement: Pending-marker election

After writing its pending intent and before calling `/api/spawn`, the dispatching
agent SHALL re-scan `raven@localhost`. If another unconfirmed pending marker for
the same persona is older — compared by Maildir arrival / `Date`, breaking ties by
`Message-ID` — the agent SHALL yield and not spawn. Only the oldest pending marker
proceeds to `/api/spawn`.

#### Scenario: Two overlapping check-ins race
- **WHEN** two check-in instances each write a pending marker for the same persona
- **THEN** each re-scans, the instance with the newer marker yields, and only the
  instance with the oldest marker calls `/api/spawn`

#### Scenario: Tie broken by Message-ID
- **WHEN** two pending markers share the same arrival time / `Date`
- **THEN** the marker with the lower `Message-ID` wins and the other yields

### Requirement: Intent staleness

The dispatching agent SHALL treat intents as blocking only while they are current:

- A **confirmed** intent is stale when `kirocrew spawn list` shows its referenced
  spawn task as completed or absent.
- A **pending** intent is stale only after one full subsequent check-in finds no
  task description carrying its intent token and no matching in-flight agent; until
  then it blocks a retry.

A stale intent SHALL NOT block a new dispatch.

#### Scenario: Confirmed intent becomes stale
- **WHEN** a confirmed intent references a spawn task that `spawn list` reports as
  completed or absent
- **THEN** the agent treats the intent as stale and it no longer blocks dispatch

#### Scenario: Pending intent held for one cycle
- **WHEN** a pending intent exists and the current check-in cannot yet find a task
  description or in-flight agent carrying its token
- **THEN** the pending intent still blocks a retry this cycle and is only declared
  stale after a full subsequent check-in confirms no matching task or agent
