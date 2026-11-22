# task-orchestration/steer Specification

## Purpose

Defines how operators steer running tasks and continue completed sessions.

## Requirements

### Requirement: Steering running or completed tasks
The system SHALL redirect a still-running task in place, and SHALL resume a completed task's session with full prior context when steered again. Steering only takes effect at a turn boundary — it SHALL NOT interrupt a tool call already in flight inside the crew, unless the caller opts into a forceful stop. `steer`'s `task_id` SHALL be limited to tasks created via `dispatch` (`/api/spawn`) — a recurring job created via `schedule` has no such `task_id` and is not steerable through this tool.

#### Scenario: Steer a running task
- **WHEN** `steer` is called with a `task_id` whose task is not yet done and `force` is not set
- **THEN** the system sends the message to the task's `/steer` endpoint and returns action `steered`

#### Scenario: Continue a completed task
- **WHEN** `steer` is called with a `task_id` whose task is already done
- **THEN** the system calls the task's `/continue` endpoint with the new message, resuming the same session with its prior context intact, and returns action `redeployed` — regardless of whether `force` was set, since there is nothing running left to stop

#### Scenario: Steering a task stuck in a blocking tool call
- **WHEN** `steer` is called for a task that is currently inside a long-running or unbounded blocking tool call (e.g. an infinite shell polling loop) and `force` is not set
- **THEN** the steer call itself succeeds (the message is accepted by the endpoint), but the message does not reach the agent until that tool call returns — which, for a genuinely unbounded loop, may never happen without `force` or external intervention (e.g. `nuke` and redispatch)

#### Scenario: Forcefully stopping a stuck task
- **WHEN** `steer` is called with `force` set to true for a `task_id` whose task is not yet done
- **THEN** the system stops the task's underlying process (rather than waiting for a turn boundary), then resumes the same session with the new message via the task's `/continue` endpoint, and returns action `force_redeployed`

#### Scenario: A recurring job has no task_id to steer
- **WHEN** an Admiral wants to change what a `schedule`-created recurring job does
- **THEN** `steer` cannot be used, since the job has a `job_id`, not a `task_id` — a new `schedule` call, or for a standing-orders Captain check-in a `captain(action="order", ...)` call, is the only path
