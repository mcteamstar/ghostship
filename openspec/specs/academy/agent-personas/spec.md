# Agent Personas Specification

## Purpose

Give every crew the same six KiroCrew agent personas — five aligned to one part of the OpenSpec explore -> propose -> apply -> archive workflow, plus Raven for standing-orders coordination — so dispatched work goes to a persona whose prompt and tool grant fit the task.

## Requirements

### Requirement: Six standard personas shipped to every crew
The system SHALL copy the agent definitions selected by the crew type's manifest (see `academy/crew-manifest`) from the `agents/` Academy pool into every crew during `launch`, defaulting to all six (Ghost, Spectre, Banshee, Wraith, Reaper, Raven) when the manifest specifies `"*"`.

#### Scenario: Crew setup copies all agent definitions
- **WHEN** a crew finishes setup
- **THEN** the crew's `~/.kiro/agents/` directory contains a JSON file for each agent name selected by that crew type's manifest, resolved against the transport container's `/agents` Academy pool bind-mount

#### Scenario: kirocrew's manifest yields today's full set
- **WHEN** a crew is stood up using the `kirocrew` crew type, whose manifest specifies `"*"` for agents
- **THEN** the crew's `~/.kiro/agents/` directory contains a JSON file for every one of Ghost, Spectre, Banshee, Wraith, Reaper, and Raven

### Requirement: Persona tool grants

Each persona SHALL receive the tool grants defined for its role, and dispatched KiroCrew sessions SHALL NOT expose a native MCP surface for subagent control.

#### Scenario: Standard personas receive role-specific tool grants
- **WHEN** the standard persona definitions are loaded
- **THEN** Ghost, Spectre, and Banshee receive `read grep glob write code shell`; Wraith receives `read grep glob shell`; Reaper receives `read grep glob write shell`; and Raven receives `read grep glob shell`, ordered read/search, write, then execute
- **AND** dispatched sessions expose no native MCP surface for subagent control; Raven uses its `shell` grant with the `kirocrew` CLI and crew gateway REST API

#### Scenario: Wraith cannot write
- **WHEN** Wraith is dispatched a task
- **THEN** Wraith's agent definition grants no `write` tool, so it can research and document but not edit code

#### Scenario: Raven cannot write or produce code changes directly
- **WHEN** Raven is dispatched (via a crew's recurring check-in job)
- **THEN** Raven's agent definition grants no `write` or `code` tool — it directs work by dispatching one of the five sanctioned personas, it does not implement anything itself
### Requirement: Raven is a sixth, coordination-only persona

Raven's base prompt SHALL cover generic crew-watching and mail coordination and SHALL omit Captain-loop-specific behavior.

#### Scenario: Base prompt covers generic crew coordination
- **WHEN** Raven is dispatched for ordinary crew work
- **THEN** its base prompt directs it to watch crew task state, write mail to any address, dispatch named personas through `ghostship-spawn`, and use `kirocrew` for routine operations, without Captain-loop rules

#### Scenario: Raven dispatched directly reads all mailboxes
- **WHEN** an Admiral dispatches Raven directly (not via Captain) to read or relay mail
- **THEN** Raven reads `/var/mail/admiral` and all persona mailboxes as a core capability, without requiring any standing order to enable this behaviour

#### Scenario: Directly dispatched Raven has an isolated session
- **WHEN** Raven is dispatched via `dispatch(agent="raven", ...)`
- **THEN** Raven runs in a dedicated KiroCrew session with no shared memory from Captain-loop check-ins, which run under the shared background session

### Requirement: Captain-loop behavior comes from the standing order

Captain-loop-only instructions SHALL be injected by the Captain standing-order template at job creation, not embedded in Raven's persona definition.

#### Scenario: Captain-loop Raven receives its loop behaviour via the standing order
- **WHEN** `captain(action="order")` creates or updates a standing-orders check-in
- **THEN** the resolved standing order message injected into the Raven dispatch contains: read `/var/mail/captain`, self-cancel when done, the order-change contract, and sanctioned persona list — none of which come from `raven.json` itself

### Requirement: Raven delegates gateway operations

Raven SHALL use `ghostship-spawn` for gateway operations that the `kirocrew` CLI does not provide.

#### Scenario: Raven's lean prompt still covers gateway auth
- **WHEN** Raven needs to dispatch a named persona, steer a task, or continue a finished task
- **THEN** Raven's base prompt directs it to the `ghostship-spawn` skill for those operations, since this is generic dispatch capability not Captain-loop-specific, and the prompt does not mention `.local_secret`, `X-Internal-Secret` or `X-Session-Key`

### Requirement: Raven honors explicit model choices for delegated tasks
When Raven is instructed to dispatch a named persona task using a specific model, Raven SHALL pass that model through `ghostship-spawn` using its `--model` option.

#### Scenario: Standing order requests a model for delegated work
- **WHEN** Raven is instructed to start a named persona task using `claude-opus-5`
- **THEN** Raven dispatches through `ghostship-spawn <persona> --model claude-opus-5`

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

### Requirement: OpenSpec invocation guidance uses backend skill syntax
When persona prompts explain how to invoke OpenSpec workflows, they SHALL name available `openspec-*` skills and use the selected backend's supported syntax; they SHALL NOT refer to removed `/opsx:*` command files.

#### Scenario: Persona prompt uses supported v2 skill invocation
- **WHEN** an agent follows an OpenSpec invocation example in a persona prompt
- **THEN** the example identifies the relevant `openspec-*` skill and uses `$openspec-*` for Codex or `/openspec-*` for a backend that supports slash skill invocation

### Requirement: Persona division is prompt-level guidance, not a technical gate
The system SHALL NOT technically restrict which `openspec-*` skills a given persona can invoke; every persona inherits every crew-wide skill by default. Only each persona's own system prompt narrows what it is meant to do.

#### Scenario: An agent invokes a skill outside its stated ownership
- **WHEN** a persona whose prompt does not mention a given `openspec-*` skill invokes that skill anyway
- **THEN** the invocation succeeds technically — the skill is available to every persona in the crew — and the only enforcement is whatever the persona's own prompt tells it to focus on

#### Scenario: A future per-persona technical boundary
- **WHEN** the project decides role-bleed between personas is a real problem
- **THEN** enforcing the "owns" division technically requires per-agent `resources`/`skill://` scoping (with `chat.disableInheritingDefaultResources` set), which is not implemented as of this spec
