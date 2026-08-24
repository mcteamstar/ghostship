## MODIFIED Requirements

### Requirement: Task pickup and progress reporting
The system SHALL report a task's progress and result when polled, and SHALL list all tasks in a crew when no specific task is named. The system SHALL always include mail state in the pickup response without requiring any flag or option. The system SHALL support an optional `timeout_secs` parameter that, when greater than zero, polls until the task completes, the timeout elapses, or new Admiral mail arrives.

The system SHALL cap the internal poll window at `GA_PICKUP_MAX_POLL_SECS` (default 30s) regardless of the caller-supplied `timeout_secs` value. When the internal cap fires before the caller's `timeout_secs` has elapsed (i.e. the task is still running), the system SHALL return the current task state as a normal (non-error) JSON response with `"reason": "timeout"`. The MCP transport error path SHALL NOT be used for a clean timeout expiry.

#### Scenario: Poll a specific task
- **WHEN** `pickup` is called with a `task_id` and `crew_id`
- **THEN** the system returns the task's done state, turn count, last tool used, elapsed seconds, result, error, and outcome, plus the unread mail count for the agent that ran the task and the Admiral mail count

#### Scenario: List all tasks in a crew
- **WHEN** `pickup` is called with a `crew_id` but no `task_id`
- **THEN** the system returns a dict containing the task list, a per-agent unread mail summary, and the Admiral mail count

#### Scenario: Poll a specific task reports agent, captain, and admiral subjects
- **WHEN** `pickup` is called with a `task_id` and `crew_id`
- **THEN** the response includes the existing fields plus `<agent>_mail: N`, `<agent>_subjects: [...]`, `captain_mail: N`, `captain_subjects: [...]`, `admiral_mail: N`, `admiral_subjects: [...]`

#### Scenario: List all tasks reports all persona, captain, and admiral subjects
- **WHEN** `pickup` is called with a `crew_id` but no `task_id`
- **THEN** the response includes subject line summaries for all persona mailboxes plus captain and admiral alongside the existing task list

#### Scenario: Poll a specific task with timeout
- **WHEN** `pickup` is called with a `task_id`, `crew_id`, and `timeout_secs` greater than zero, and the task completes before both `timeout_secs` and `GA_PICKUP_MAX_POLL_SECS` elapse
- **THEN** the system polls until the task is done, then returns the same shape as a zero-timeout pickup including mail state

#### Scenario: Timeout elapses before the task finishes
- **WHEN** `pickup` is called with a `task_id`, `crew_id`, and `timeout_secs` greater than zero, and the task is still not done when the poll window ends
- **THEN** the system returns the task's current (not-done) state as a **normal JSON response** (not a transport error) including mail state, with `"reason": "timeout"` in the response body

#### Scenario: Internal poll cap fires before caller timeout_secs
- **WHEN** `pickup` is called with `timeout_secs` greater than `GA_PICKUP_MAX_POLL_SECS` and the task does not complete within `GA_PICKUP_MAX_POLL_SECS`
- **THEN** the system returns the current task state as a normal JSON response with `"reason": "timeout"` — the caller MAY re-poll with another `pickup(timeout_secs=N)` call to continue waiting

#### Scenario: Early return on Admiral mail during polling
- **WHEN** `pickup` is called with `timeout_secs` greater than zero, and new Admiral mail arrives while polling
- **THEN** the system returns early with the current task state and `reason: "admiral_mail"` alongside the normal response fields

#### Scenario: Default timeout is zero (immediate return)
- **WHEN** `pickup` is called without specifying `timeout_secs`
- **THEN** the system checks once and returns immediately, defaulting `timeout_secs` to 0
