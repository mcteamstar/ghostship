# task-orchestration/pickup Specification

## Purpose

Defines task status, polling and result collection.

## Requirements

### Requirement: Task status and collection
Polling SHALL report task progress and result; omitting the task ID SHALL list all crew tasks. `pickup` SHALL wait only when `timeout_secs > 0`, ending on completion, timeout, or new Admiral mail. Its cap is `GA_PICKUP_MAX_POLL_SECS` (default 30s); cap expiry SHALL return normal JSON with `reason: timeout`. Each call reads all eight mailboxes without modifying them and returns subjects/counts only: task-specific calls report that agent, Captain, and Admiral; crew-wide calls report all eight.

#### Scenario: Poll a specific task
- **WHEN** `pickup` is called with a `task_id` and `crew_id`
- **THEN** the system returns the task's done state, turn count, last tool used, elapsed seconds, result, error, and outcome, plus the unread mail count for the agent that ran the task and the Admiral mail count, and `created_at`, `started_at`, `completed_at` ISO 8601 UTC timestamps (`null` when not yet reached)

#### Scenario: List all tasks in a crew
- **WHEN** `pickup` is called with a `crew_id` but no `task_id`
- **THEN** the system returns a dict containing the task list, a per-agent unread mail summary, and the Admiral mail count

#### Scenario: Poll a specific task reports agent, captain, and admiral subjects
- **WHEN** `pickup` is called with a `task_id` and `crew_id`
- **THEN** the response includes the existing fields plus `<agent>_mail: N`, `<agent>_subjects: [...]`, `captain_mail: N`, `captain_subjects: [...]`, `admiral_mail: N`, `admiral_subjects: [...]`

#### Scenario: List all tasks reports all persona, captain, and admiral subjects
- **WHEN** `pickup` is called with a `crew_id` but no `task_id`
- **THEN** the response includes `agent_subjects` with subject line summaries for all 8 mailboxes plus captain and admiral alongside the existing task list

#### Scenario: pickup with agent filter returns single-inbox subjects only
- **WHEN** `pickup` is called without a `task_id` and with `agent="ghost"`
- **THEN** the response includes only ghost's mailbox subjects and count — no task list, no other mailbox data

#### Scenario: pickup with agent filter for an empty mailbox
- **WHEN** `pickup` is called without a `task_id` and with `agent="reaper"` and reaper's mailbox is empty
- **THEN** the response includes `{"agent": "reaper", "subjects": [], "mail": 0}`

#### Scenario: pickup with invalid agent name returns an error
- **WHEN** `pickup` is called with `agent="admiral"` (not a persona mailbox)
- **THEN** the system returns an error indicating the agent name is not valid for this filter

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

### Requirement: Blocking wait on a single task
The system SHALL provide a `bridge` tool as a backward-compatible alias for `pickup(timeout_secs=...)`. `bridge` delegates entirely to `pickup` and preserves the same interface for existing callers. New callers SHOULD use `pickup(timeout_secs=...)` directly.

#### Scenario: Task finishes before the timeout
- **WHEN** `bridge` is called with a `task_id`, `crew_id`, and `timeout_secs`, and the task completes before `timeout_secs` elapses
- **THEN** the system returns the task's done state and mail counts as soon as `done` becomes `true`

#### Scenario: Timeout elapses before the task finishes
- **WHEN** `bridge` is called with a `task_id` and the task is still not done after `timeout_secs` has elapsed
- **THEN** the system returns the task's current (not-done) state without raising an error

#### Scenario: Crew is idle-stopped when bridge is called
- **WHEN** `bridge` is called against a crew that is currently idle-stopped
- **THEN** the system restarts the crew before beginning to poll, the same recovery `pickup` and `supply` already perform

#### Scenario: Waiting for any task in a crew to finish
- **WHEN** `bridge` is called with a `crew_id` but no `task_id`, and at least one task in that crew completes before `timeout_secs` elapses
- **THEN** the system returns that task's result as soon as any task's `done` becomes `true`

#### Scenario: Timeout elapses with no task done and no task_id given
- **WHEN** `bridge` is called with a `crew_id` but no `task_id`, and no task in that crew is done after `timeout_secs` has elapsed
- **THEN** the system returns the full crew task dict in the same shape `pickup` returns when called without a `task_id`

#### Scenario: Bridge does not accept multi-crew or multi-task requests
- **WHEN** `bridge` is called without a specific `crew_id`
- **THEN** the system returns a validation error

### Requirement: Batch lookup matches task ID subsets

`_find_batch_by_task_ids` SHALL match when every provided ID belongs to a recorded batch; a strict superset or disjoint set SHALL NOT match.

#### Scenario: Batch lookup — subset match

- **WHEN** `pickup(task_ids=[id1, id2])` is called and a registered batch contains `[id1, id2, id3]`
- **THEN** the batch is found and returned (subset of batch task IDs matches)

#### Scenario: Batch lookup — exact match still works

- **WHEN** `pickup(task_ids=[id1, id2, id3])` is called and a registered batch contains exactly `[id1, id2, id3]`
- **THEN** the batch is found and returned

#### Scenario: Batch lookup — superset does not match

- **WHEN** `pickup(task_ids=[id1, id2, id3, id4])` is called and a registered batch contains only `[id1, id2, id3]`
- **THEN** no batch is returned (caller passed more IDs than the batch holds)

#### Scenario: Batch lookup — disjoint does not match

- **WHEN** `pickup(task_ids=[id_x, id_y])` is called and no batch contains either ID
- **THEN** no batch is returned

### Requirement: Lost-member detection

When `pickup` is called with `task_ids` and one or more of the listed IDs has no record in the gateway (i.e. `/api/spawn/<id>` returns 404), the system SHALL mark that task as `lost` in the response rather than raising an error for the whole batch. A `lost` task result SHALL include `{"task_id": "<id>", "done": false, "lost": true, "error": "task not found in gateway"}`. The overall batch result SHALL still be returned; the `done` field for the batch SHALL be `false` when any member is lost.

#### Scenario: One task lost mid-batch

- **WHEN** `pickup` is called with `task_ids=["id1", "id2"]` and `id2` returns 404 from the gateway
- **THEN** the response includes a normal result for `id1` and `{"task_id": "id2", "done": false, "lost": true, "error": "task not found in gateway"}` for `id2`, and the overall `done: false`

### Requirement: Pickup reports mailbox subjects and counts

Pickup SHALL expose mailbox subjects and counts for task-specific and crew-wide queries without returning message bodies or modifying mailbox files. Crew-wide pickup SHALL allow filtering to one valid persona. See `captain/mail` for Captain status.

#### Scenario: Pickup on a specific task includes supporting mail
- **WHEN** a Ghost task is queried and Ghost, Raven, Captain and Admiral have mail
- **THEN** pickup includes `agent_mail`, `ghost_subjects`, `raven_subjects`, `captain_mail`, `captain_subjects`, `admiral_mail` and `admiral_subjects`

#### Scenario: Crew-wide pickup reports mailbox summaries
- **WHEN** pickup is called without a task ID or agent filter
- **THEN** it includes all mailbox subject summaries in `agent_subjects`, non-empty persona counts in `mail_summary`, and explicit Captain and Admiral subjects and counts

#### Scenario: Pickup filtered by persona
- **WHEN** crew-wide pickup is filtered to a valid persona
- **THEN** it returns only that persona's `agent`, `subjects` and `mail`, using an empty list and zero if the mailbox is empty

#### Scenario: Pickup filtered by a non-persona mailbox
- **WHEN** crew-wide pickup is filtered to an invalid persona such as Admiral
- **THEN** it returns a validation error

#### Scenario: Empty mailbox summaries
- **WHEN** a mailbox is empty
- **THEN** its explicit summary uses zero and an empty list; optional per-persona summary entries may be omitted

### Requirement: Batch pickup polls and returns results by task ID

The `pickup` tool SHALL accept a nonempty `task_ids` list instead of `task_id`. It SHALL poll each member once per round and return one result per ID. A zero timeout returns a snapshot; a positive timeout polls until all members complete, the capped poll window expires, or Admiral mail arrives. Batch lookup and lost-member reporting follow their own requirements.

#### Scenario: Blocking batch pickup — all tasks complete before timeout

- **WHEN** `pickup` is called with `task_ids=["id1", "id2"]`, `crew_id`, and `timeout_secs=300`, and both tasks complete before the timeout
- **THEN** the system returns `{"id1": {<full single-task pickup shape>}, "id2": {<full single-task pickup shape>}, "done": true, "completed_tasks": 2, "total_tasks": 2}`

#### Scenario: Blocking batch pickup — timeout fires before all tasks complete

- **WHEN** `pickup` is called with `task_ids=[...]`, `crew_id`, and `timeout_secs=N`, and at least one task is not done when the poll window ends
- **THEN** the system returns the collected results for all tasks (done and not-done) with `"reason": "timeout"`, `"done": false`, and per-task `done` flags in each task result

#### Scenario: Blocking batch pickup — Admiral mail early-return

- **WHEN** `pickup` is called with `task_ids=[...]` and `timeout_secs > 0`, and new Admiral mail arrives while polling
- **THEN** the system returns early with current per-task state and `"reason": "admiral_mail"`

#### Scenario: Blocking batch pickup — timeout_secs == 0 returns snapshot

- **WHEN** `pickup` is called with `task_ids=[...]` and `timeout_secs=0` (default)
- **THEN** the system queries each task once and returns their current states without blocking — no `reason` field is included unless a task individually has one

#### Scenario: task_id and task_ids both supplied

- **WHEN** `pickup` is called with both `task_id` and `task_ids` set
- **THEN** the system returns `{"error": "Provide either task_id or task_ids, not both"}`

#### Scenario: Batch pickup with empty task_ids list

- **WHEN** `pickup` is called with `task_ids=[]`
- **THEN** the system returns `{"error": "task_ids must not be empty"}`

#### Scenario: pickup(task_ids=...) inherits the existing timeout cap

- **WHEN** `pickup` is called with `task_ids=[...]` and `timeout_secs` greater than `GA_PICKUP_MAX_POLL_SECS`
- **THEN** each polling round completes within `GA_PICKUP_MAX_POLL_SECS`, the system returns with `"reason": "timeout"`, and the caller may re-poll to continue waiting — identical to the single-task `pickup` internal-cap behaviour

#### Scenario: pickup(task_ids=...) without crew_id returns an error

- **WHEN** `pickup` is called with `task_ids=[...]` and no `crew_id`
- **THEN** the system reports that a crew ID is required, using the same validation as single-task pickup
