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
The system SHALL define Raven as a persona distinct in kind from the other five: the Captain is the recurring check-in loop itself, and Raven is the persona that loop dispatches to watch over a crew's standing orders, assess what is actually happening each cycle, and communicate the right order to the right worker — not to explore, implement, review, or archive OpenSpec work itself. Raven's prompt SHALL instruct it to restrict any dispatch it makes to the five sanctioned persona names (`ghost`, `spectre`, `banshee`, `wraith`, `reaper`) — a prompt-level restriction, since Raven composes its own authenticated `POST` to the crew gateway's `/api/spawn` (see `autonomous-orchestration`) and this system does not gate that call's `agent` value in code, the same category of trade-off `Persona division is prompt-level guidance, not a technical gate` already documents for the other five.

#### Scenario: Raven is explicitly selected for Captain check-ins
- **WHEN** `captain(crew_id, action="order", ...)` creates or reuses a standing-orders check-in job
- **THEN** the job dispatches Raven because the Captain check-in explicitly selects that coordination persona; generic `schedule()` calls default to Ghost

#### Scenario: Raven restricts its own dispatches by prompt, not by a technical gate
- **WHEN** Raven decides to dispatch a persona for the next atomic step
- **THEN** its own system prompt instructs it to name only one of the five sanctioned personas in that request, and nothing in this system technically prevents it from naming another agent — the same accepted limitation as any other persona's prompt-level scoping

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
