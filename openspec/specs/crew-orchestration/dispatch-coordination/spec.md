# crew-orchestration/dispatch-coordination Specification

## Purpose
Defines the coordination rules a dispatching agent (Raven) must follow so that a
single SDD lifecycle transition produces exactly one persona dispatch, even when
check-in cycles overlap.

## Requirements

### Requirement: Layered 3-signal pre-dispatch check

Before an SDD dispatch, the agent SHALL check mailbox intents, the `task` description's `SDD dispatch <intent_id> <change> <persona>` prefix, then the `agent` field as tertiary confirmation. If the task description is truncated after the intent token, the mailbox body SHALL be used to resolve its change/persona key; it MUST dispatch only when all signals are clear.

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
  with `SDD dispatch <intent_id> <change> <persona>` for the same change and persona
- **THEN** the dispatching agent holds and does not dispatch

#### Scenario: Agent field alone does not authorize a dispatch
- **WHEN** the agent field is empty but a non-stale mailbox intent or matching
  task-description marker exists
- **THEN** the dispatching agent holds; a clear agent field alone is insufficient
  to proceed

### Requirement: Unreadable intent mailbox blocks dispatch

If `raven@localhost` is unavailable or unreadable, the agent SHALL hold and MUST NOT dispatch until a later check-in.

#### Scenario: Mailbox unavailable is a hold condition
- **WHEN** the mailbox (`raven@localhost`) cannot be read (unavailable or access error)
- **THEN** the dispatching agent holds and does not dispatch; a missing or
  unreadable mailbox is treated the same as a blocking signal, not as a clear one
### Requirement: Intent marker precedes spawn

After all signals clear, the agent SHALL generate `intent-<uuid>`, prefix the worker task with `SDD dispatch <intent_id> <change> <persona>`, and mail `dispatching <persona> <intent_id>` from `raven+<raven_task_id>@localhost` before `/api/spawn`; it MUST NOT invent the gateway ID.

#### Scenario: Pending marker precedes spawn
- **WHEN** the agent decides to dispatch a persona
- **THEN** it writes the pending intent message to `raven@localhost` before
  calling `/api/spawn`

### Requirement: Intent marker is confirmed after spawn

After success, the agent SHALL mail `dispatching <persona> <spawn_task_id>` using the gateway ID and link the intent in the body; on failure it SHALL write no confirmation.

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
