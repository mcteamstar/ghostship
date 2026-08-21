# Agent Personas Specification

## Purpose

Give every crew the same six KiroCrew agent personas — five aligned to one part of the OpenSpec explore -> propose -> apply -> archive workflow, plus Raven for standing-orders coordination — so dispatched work goes to a persona whose prompt and tool grant fit the task.

## Requirements

### Requirement: Six standard personas shipped to every crew
The system SHALL copy the agent definitions selected by the crew type's manifest (see `crew-manifest`) from the `agents/` Academy pool into every crew during `launch`, defaulting to all six (Ghost, Spectre, Banshee, Wraith, Reaper, Raven) when the manifest specifies `"*"`.

#### Scenario: Crew setup copies all agent definitions
- **WHEN** a crew finishes setup
- **THEN** the crew's `~/.kiro/agents/` directory contains a JSON file for each agent name selected by that crew type's manifest, resolved against the transport container's `/agents` Academy pool bind-mount

#### Scenario: kirocrew's manifest yields today's full set
- **WHEN** a crew is stood up using the `kirocrew` crew type, whose manifest specifies `"*"` for agents
- **THEN** the crew's `~/.kiro/agents/` directory contains a JSON file for every one of Ghost, Spectre, Banshee, Wraith, Reaper, and Raven

### Requirement: Persona tool grants
The system SHALL grant each persona a distinct tool set matching its role, all drawn from one consistent ordering (read/search, then write, then execute): Ghost, Spectre, and Banshee get `read grep glob write code shell`; Wraith gets read-only tools (`read grep glob shell`, no `write`); Reaper gets `read grep glob write shell` (no `code`); Raven gets read-only tools (`read grep glob shell`, no `write`, no `code`). A dispatched KiroCrew session exposes no native MCP surface for subagent control regardless of persona — Raven directs work through its `shell` grant alone, using the `kirocrew` CLI and the crew gateway's own REST API (see `autonomous-orchestration`), not a tool grant distinct from the other four's.

#### Scenario: Wraith cannot write
- **WHEN** Wraith is dispatched a task
- **THEN** Wraith's agent definition grants no `write` tool, so it can research and document but not edit code

#### Scenario: Raven cannot write or produce code changes directly
- **WHEN** Raven is dispatched (via a crew's recurring check-in job)
- **THEN** Raven's agent definition grants no `write` or `code` tool — it directs work by dispatching one of the five sanctioned personas, it does not implement anything itself

### Requirement: Raven is a sixth, coordination-only persona
The system SHALL define Raven as a lean, general-purpose watcher and messenger persona. Raven's prompt SHALL describe only generic crew-watching and mail behaviour: reading all mailboxes (including Admiral), writing mail to any address, watching crew task state, dispatching named personas via the crew gateway REST API, and using the `kirocrew` CLI for routine ops. Raven's prompt SHALL NOT embed Captain-loop-specific behaviour (self-cancellation, standing-order ownership, OpenSpec store resolution, or cron job management).

Captain-loop-specific behaviour — reading `/var/mail/captain`, self-cancelling when standing orders are met, the order-change contract, sanctioned persona list for dispatch, and OpenSpec store resolution — SHALL be injected by the Captain standing-order template at job creation time, not baked into the persona definition.

Raven's prompt SHALL retain guidance on the four operations that require direct gateway REST API calls (dispatch a named persona, get per-task detail, steer a running task, continue a finished task) and how to authenticate those calls.

#### Scenario: Raven dispatched directly reads all mailboxes
- **WHEN** an Admiral dispatches Raven directly (not via Captain) to read or relay mail
- **THEN** Raven reads `/var/mail/admiral` and all persona mailboxes as a core capability, without requiring any standing order to enable this behaviour

#### Scenario: Captain-loop Raven receives its loop behaviour via the standing order
- **WHEN** `captain(action="order")` creates or updates a standing-orders check-in
- **THEN** the resolved standing order message injected into the Raven dispatch contains: read `/var/mail/captain`, self-cancel when done, the order-change contract, and sanctioned persona list — none of which come from `raven.json` itself

#### Scenario: Directly dispatched Raven has an isolated session
- **WHEN** Raven is dispatched via `dispatch(agent="raven", ...)`
- **THEN** Raven runs in a dedicated KiroCrew session with no shared memory from Captain-loop check-ins, which run under the shared background session

#### Scenario: Raven's lean prompt still covers gateway auth
- **WHEN** Raven needs to dispatch a named persona, steer a task, or continue a finished task
- **THEN** Raven's base prompt provides guidance on using the gateway REST API with `.local_secret` authentication, since this is generic dispatch capability not Captain-loop-specific

### Requirement: OpenSpec workflow division by persona
The system SHALL scope each persona's prompt to the intended OpenSpec workflow division: Spectre to explore/propose/update-change, Ghost to all six operations with apply-change as its implementation path, Banshee to explore/propose/update-change/apply-change for independent review and fixes, and Reaper to sync-specs/archive-change. Banshee SHALL hand specification synchronization and change archival to Reaper rather than owning those close-out operations.

#### Scenario: Spectre plans, Ghost implements
- **WHEN** a change needs to move from idea to implementation
- **THEN** Spectre is the persona whose prompt directs it to explore and propose, while Ghost's prompt directs it to implement an already-proposed change's tasks

#### Scenario: Banshee finds and fixes independently
- **WHEN** Banshee is dispatched to review work across a wider scope than a single task
- **THEN** Banshee's prompt permits explore, propose, update-change, and apply-change, while directing sync-specs and archive-change to Reaper

#### Scenario: Reaper closes the change
- **WHEN** implementation and independent review are complete
- **THEN** Reaper is the persona whose prompt directs it to synchronize approved specs and archive the completed change

### Requirement: Persona division is prompt-level guidance, not a technical gate
The system SHALL NOT technically restrict which `openspec-*` skills a given persona can invoke; every persona inherits every crew-wide skill by default. Only each persona's own system prompt narrows what it is meant to do.

#### Scenario: An agent invokes a skill outside its stated ownership
- **WHEN** a persona whose prompt does not mention a given `openspec-*` skill invokes that skill anyway
- **THEN** the invocation succeeds technically — the skill is available to every persona in the crew — and the only enforcement is whatever the persona's own prompt tells it to focus on

#### Scenario: A future per-persona technical boundary
- **WHEN** the project decides role-bleed between personas is a real problem
- **THEN** enforcing the "owns" division technically requires per-agent `resources`/`skill://` scoping (with `chat.disableInheritingDefaultResources` set), which is not implemented as of this spec
