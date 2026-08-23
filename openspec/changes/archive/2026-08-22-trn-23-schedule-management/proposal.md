# Proposal: trn-23-schedule-management

## Why

The `schedule` tool creates recurring jobs but provides no Admiral-side way to cancel or list them. Cancelling a job currently requires dispatching a Ghost inside the crew to kill it manually — a poor UX that also requires knowing the internal job management API. There is also no one-shot "fire after delay" primitive, forcing a workaround of schedule-then-cancel.

## What Changes

- Add `cancel` action to the `schedule` tool — cancel a job by `job_id`
- Add `list` action to the `schedule` tool — list all active scheduled jobs for a crew with `job_id`, `name`, `schedule`, `agent`, and `last_run`
- Add `fire_after_secs` parameter to `dispatch` — schedule a one-shot task to fire once after a delay, without creating a repeating job

## Capabilities

### Modified Capabilities

- `task-orchestration` — The Admiral can now cancel scheduled jobs and list what is running. One-shot delayed dispatch is a new primitive that completes the dispatch/schedule matrix.

## Impact

- `transport/server.py` — `schedule` tool handler (new `cancel` and `list` actions), `dispatch` tool handler (`fire_after_secs` parameter)
- `transport/test_transport.py` — new tests for cancel, list, and delayed dispatch
- `transport://agents` or a new `transport://jobs` resource — expose scheduled job list to MCP clients
- README tools table — update `schedule` and `dispatch` descriptions
