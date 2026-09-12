# ACP Prewarm Specification

## Purpose

Pre-establish a crew's ACP session connection ahead of an expected dispatch, so the cold-start cost of forking the `kiro-cli-chat` session and completing the ACP handshake is hidden behind a controlled warm-up rather than charged to the first user-visible task — while preserving the idle-memory savings of deferred (non-eager) session spawn.

## Requirements

### Requirement: Prewarm operation establishes a warm ACP session

The transport SHALL expose a `prewarm` operation that, for a named running-or-startable crew, ensures the crew container is running and its `kiro-cli-chat` session process is forked with a completed ACP handshake, so that a subsequent `dispatch` on that crew does not pay session cold-start latency. The operation SHALL return promptly with a status describing the crew's warm state; it SHALL NOT block until any real task completes, and it SHALL NOT dispatch real agent work.

The operation SHALL be exposed both as an MCP tool (`prewarm`) and as a REST endpoint (`POST /crews/{crew_id}/prewarm`), and the REST endpoint SHALL respect the same `GA_API_KEY` authentication as the other crew REST endpoints.

#### Scenario: Prewarm a stopped crew
- **WHEN** `prewarm` is called for a registered crew whose container is stopped, and the memory and active-crew gates permit a start
- **THEN** the transport starts the container, waits for the gateway to become ready, causes the session process to be forked with a completed ACP handshake, and returns a status indicating the crew is now warm

#### Scenario: Prewarm returns without blocking on real work
- **WHEN** `prewarm` is called for a crew
- **THEN** the call returns once the session is warm (or a gate/error condition is hit), and no `dispatch` of real agent work is issued as part of the operation

#### Scenario: Prewarm exposed over REST with auth
- **WHEN** `POST /crews/{crew_id}/prewarm` is called with a valid `GA_API_KEY`
- **THEN** the request is accepted and behaves identically to the `prewarm` MCP tool for that crew

#### Scenario: Prewarm REST rejects missing or invalid auth
- **WHEN** `POST /crews/{crew_id}/prewarm` is called without a valid `GA_API_KEY` while auth is enabled
- **THEN** the request is rejected with an authentication error and no container start or session fork is performed

### Requirement: Prewarm is idempotent and non-destructive

Prewarming a crew whose session is already warm SHALL be a cheap no-op that reports the already-warm state rather than forking a second session or restarting the container. The prewarm operation SHALL NOT mutate crew workspace state: it SHALL NOT modify specs, write files into the workspace, send mail, or alter the crew registry beyond the activity/warm bookkeeping the transport already performs for a normal auto-start.

#### Scenario: Prewarm an already-warm crew
- **WHEN** `prewarm` is called for a crew whose session process is already forked and its ACP connection already established
- **THEN** the transport performs no container restart and no second session fork, and returns a status indicating the crew was already warm

#### Scenario: Prewarm does not perform real work
- **WHEN** `prewarm` completes for any crew
- **THEN** no spec is modified, no file is written into the crew workspace by the operation, and no mail is sent as a side effect of prewarming

#### Scenario: Prewarm an unknown crew
- **WHEN** `prewarm` is called with a `crew_id` that has no registry entry
- **THEN** the transport returns an error and takes no action

### Requirement: Prewarm respects memory and active-crew gates

The prewarm operation SHALL be gated by the same host-memory and active-crew limits that gate starting a crew for a real dispatch. It SHALL NOT start a container or fork a session when doing so would violate `GA_MIN_FREE_MEM_GB` or `GA_MAX_ACTIVE_CREWS`. When a gate blocks the warm-up, prewarm SHALL return a human-readable status naming the gate that blocked it, without crashing or triggering an out-of-memory condition.

#### Scenario: Prewarm blocked by insufficient memory
- **WHEN** `prewarm` is called for a stopped crew and available host memory remains below `GA_MIN_FREE_MEM_GB` for the memory-wait window
- **THEN** the transport does not start the container, and prewarm returns a status naming insufficient memory as the reason

#### Scenario: Prewarm blocked by active-crew limit
- **WHEN** `prewarm` is called for a stopped crew and `GA_MAX_ACTIVE_CREWS` crew containers are already running
- **THEN** the transport does not start the container, and prewarm returns a status naming the active-crew limit as the reason

#### Scenario: Prewarm skips gates for an already-running warm crew
- **WHEN** `prewarm` is called for a crew that is already running and warm
- **THEN** the active-crew gate is not re-evaluated against that crew and the operation returns the already-warm status

### Requirement: Warmed session is reaped by the existing idle timer

A session forked by prewarm SHALL remain subject to the crew's existing `session.timeout_secs` idle reaping. If no dispatch follows a prewarm within the idle timeout, the warmed session SHALL be reaped exactly as an unused post-dispatch session would be, so prewarming cannot pin session memory indefinitely.

#### Scenario: Warmed session reaped when no dispatch follows
- **WHEN** a crew is prewarmed and no task is dispatched before `session.timeout_secs` elapses
- **THEN** the warmed session process is reaped and the crew container RSS returns to its idle baseline

#### Scenario: Dispatch shortly after prewarm reuses the warm session
- **WHEN** a task is dispatched on a crew within the idle timeout after a successful prewarm
- **THEN** the dispatch reuses the already-warm session and ACP connection and does not pay session cold-start latency again

### Requirement: Prewarm is operator-gated and configurable

Prewarm behaviour SHALL be controlled by operator environment variables with headless-safe defaults. A `GA_PREWARM_ENABLED` flag SHALL default to disabled; when disabled, the prewarm MCP tool and REST endpoint SHALL return a status indicating prewarm is disabled and SHALL perform no container start or session fork. A `GA_PREWARM_TTL_SECS` warm-lifetime hint SHALL bound how long a warm session is considered fresh for reporting purposes and SHALL NOT exceed the effective `session.timeout_secs`. Both variables SHALL be documented in `docs/configuration.md`.

#### Scenario: Prewarm disabled by default
- **WHEN** `GA_PREWARM_ENABLED` is unset and `prewarm` is called
- **THEN** the operation performs no container start or session fork and returns a status indicating prewarm is disabled

#### Scenario: Prewarm enabled by operator
- **WHEN** `GA_PREWARM_ENABLED=true` and `prewarm` is called for a startable crew within the memory and active-crew gates
- **THEN** the operation proceeds to warm the crew's ACP session

#### Scenario: Warm-lifetime hint bounded by session timeout
- **WHEN** `GA_PREWARM_TTL_SECS` is set to a value greater than the effective `session.timeout_secs`
- **THEN** the effective warm-lifetime hint used by prewarm is capped at `session.timeout_secs`

#### Scenario: Configuration variables documented
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** `GA_PREWARM_ENABLED` and `GA_PREWARM_TTL_SECS` are documented with their defaults and effect
