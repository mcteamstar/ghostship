## Why

The Admiral has no reliable way to answer "what happened when?" from MCP tool results alone. `pickup` returns `elapsed_secs` but no wall-clock anchors, so you can't tell if a task completed 2 minutes ago or 2 hours ago. Mail is the one exception — it's timestamped by the protocol — but those timestamps aren't surfaced in tool responses. The `crews` list doesn't say when a crew was last active. `captain status` doesn't say when the last check-in fired. Reconstructing a timeline currently requires digging through raw container logs.

## What Changes

- `pickup` (task) response includes `created_at`, `started_at`, and `completed_at` ISO timestamps alongside the existing `elapsed_secs`.
- `pickup` (crew-wide, no task_id) task list entries include the same timestamp fields.
- `dispatch` response includes `created_at`.
- Mail subject listings (in `pickup`, `captain status`) include a `received_at` timestamp per subject derived from the Maildir message `Date` header.
- `crews` list includes `created_at` for each crew (already stored in `crews.json`) and `last_task_at` when a task was last dispatched or completed.
- `captain status` includes `last_checkin_at` — when the most recent Raven check-in fired.

## Capabilities

### New Capabilities

- `task-timestamps`: Wall-clock timestamps on task lifecycle events exposed via `pickup` and `dispatch`.
- `mail-timestamps`: Per-message `received_at` surfaced alongside subject lines in all mail-reading responses.

### Modified Capabilities

- `task-orchestration`: `pickup` and `dispatch` responses gain timestamp fields.
- `trn-captain-mail`: `captain status` subject listings gain `received_at`; response gains `last_checkin_at`.
- `crew-lifecycle`: `crews` list response gains `created_at` and `last_task_at` per crew.

## Impact

- `transport/server.py` — `pickup`, `dispatch`, `crews` response shapes extended with timestamp fields.
- `transport/captain.py` — `captain status` response extended with `last_checkin_at` and per-subject `received_at`.
- Timestamp fields are additive — no existing field removed or renamed. No breaking changes.
- `crews.json` registry already stores `created_at`; `last_task_at` is a new field written on dispatch and task completion.
