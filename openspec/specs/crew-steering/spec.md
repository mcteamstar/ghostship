# Crew Steering Specification

## Purpose

Give every dispatched task the same crew-wide operational context — regardless of which persona runs it or what its prompt says — by exploiting kiro-cli's hardwired steering-doc path, which is loaded for every session no matter the working directory.

## Requirements

### Requirement: Steering docs copied on every launch
The system SHALL copy the steering docs selected by the crew type's manifest (see `crew-manifest`) from the `steering/` Academy pool into the crew container's `~/.kiro/steering/` directory during crew setup, defaulting to every `.md` file when the manifest specifies `"*"`.

#### Scenario: Crew setup copies steering docs
- **WHEN** a crew finishes setup
- **THEN** the crew's `~/.kiro/steering/` directory contains a file for every steering doc name selected by that crew type's manifest, resolved against the transport container's `/steering` Academy pool bind-mount

#### Scenario: kirocrew's manifest yields today's full set
- **WHEN** a crew is stood up using the `kirocrew` crew type, whose manifest specifies `"*"` for steering
- **THEN** every `.md` file present in the transport container's `/steering` Academy pool bind-mount is written into the crew's `~/.kiro/steering/` directory

### Requirement: Steering applies regardless of working directory or persona
The system SHALL rely on kiro-cli loading every file under `~/.kiro/steering/` for every session, independent of the dispatched task's own `subagent_*/` working directory or which persona is running.

#### Scenario: A dispatched task reads steering context
- **WHEN** any persona is dispatched a task in a crew that has steering docs copied in
- **THEN** the content of those docs is part of that task's session context, even though the task itself runs from an isolated per-task working directory unrelated to `~/.kiro/steering/`

### Requirement: Steering content stays environment-scoped, not project-scoped
Steering docs SHALL cover crew-wide environment facts every persona needs regardless of its own prompt (working-directory isolation, the shared OpenSpec store, when to use radio) — not project-specific conventions, which belong in whatever repository the caller delivers into `repo/`.

#### Scenario: Project conventions are not duplicated into steering
- **WHEN** a caller delivers a project repo into the crew workspace
- **THEN** that repo's own conventions are discovered by agents reading the repo directly, not injected via the crew-wide steering docs

### Requirement: Steering warns against unbounded blocking loops
Steering docs SHALL instruct every persona to avoid open-ended blocking polling loops in shell (a loop with no fixed iteration cap and no exit condition reachable from outside the loop), because `steer` cannot interrupt a tool call already in flight and such a loop cannot be redirected once started.

#### Scenario: An agent needs to wait on another agent's output
- **WHEN** a persona's task depends on output that another task may produce later
- **THEN** the steering doc's guidance directs it toward a bounded retry loop with a fixed iteration cap, or radio's send-and-continue pattern — not an unbounded `while true` poll and not `schedule`, since a recurring job can't fire once the crew has idle-stopped between runs

### Requirement: Steering documents all verify-admiral-sig exit codes
Steering docs SHALL document all three exit codes from `verify-admiral-sig` and specify the correct response to each. Exit code 2 (secret not found) SHALL be described as a transient condition — the correct response is to hold the current cycle and retry on the next check-in, not to escalate to Admiral.

#### Scenario: Exit code 0 — valid signature
- **WHEN** `verify-admiral-sig` exits 0
- **THEN** the message is genuine Admiral mail and Raven acts on it as a standing order

#### Scenario: Exit code 1 — signature mismatch
- **WHEN** `verify-admiral-sig` exits 1
- **THEN** the message is treated as crew correspondence (not an Admiral order), regardless of the `From:` header — Raven does not escalate to Admiral

#### Scenario: Exit code 2 — secret not found (transient)
- **WHEN** `verify-admiral-sig` exits 2
- **THEN** Raven holds the current cycle without escalating — the secret may not yet be readable due to a brief post-launch race; the next check-in will retry

### Requirement: verify-admiral-sig retries before returning exit code 2
The `verify-admiral-sig` script SHALL attempt to read the secret file up to 3 times with a 2-second pause between attempts before returning exit code 2. This absorbs the post-launch secret-file race within a single check-in.

#### Scenario: Secret available on second attempt
- **WHEN** the secret file is not present on the first read but appears within 4 seconds
- **THEN** `verify-admiral-sig` reads it on a retry and proceeds to signature verification normally

#### Scenario: Secret still absent after retries
- **WHEN** the secret file is absent across all retry attempts
- **THEN** `verify-admiral-sig` exits 2 after the final attempt
