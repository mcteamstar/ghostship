# Spec Delta

## ADDED Requirements

### Requirement: Transport spawns name the crew's recorded backend

Every `POST /api/spawn` the transport sends to a crew gateway (single dispatch,
batch dispatch and Captain check-in) SHALL include a `backend` field naming the
crew's recorded `acp_backend` in KiroCrew's request spelling, so the task runs on
that backend and not on one the gateway would inherit from the parent session.

#### Scenario: dispatch to a kiro crew names kiro

- **WHEN** `dispatch` sends a task to a crew whose registry entry records
  `acp_backend: "kiro"`, or records no backend
- **THEN** the `/api/spawn` body contains `"backend": "kiro"`
- **AND** never `"kas"` or another gateway-internal name.

#### Scenario: dispatch to a claude or codex crew names that backend

- **WHEN** `dispatch` sends a task to a crew recording `acp_backend: "claude"` or
  `"codex"`
- **THEN** the `/api/spawn` body names that same backend.

#### Scenario: member-slot parent does not change the runtime

- **WHEN** a dispatch is routed into a member slot
  (`parent_session="dashboard:member-<agent>"`)
- **AND** that gateway session has a different harness pick recorded
- **THEN** the task runs on the crew's recorded backend, because the body names it.

#### Scenario: batch dispatch and Captain check-in name the backend

- **WHEN** a batch dispatch sends its tasks, or Captain dispatches a Raven
  check-in, to a crew
- **THEN** every `/api/spawn` body names the crew's recorded backend.

#### Scenario: gateway refuses the named backend

- **WHEN** the gateway rejects the spawn because the named backend cannot start
- **THEN** `dispatch` returns an error carrying the gateway's refusal
- **AND** the transport does not resend the task without a `backend` field.

#### Scenario: in-crew nested spawns are unaffected

- **WHEN** an agent inside a crew spawns a sub-task with the `ghostship-spawn`
  helper
- **THEN** that request is not changed by this requirement, and inherits its
  parent's harness as the gateway decides.
