## Why

`captain status` currently returns subjects only from `captain@localhost` and `admiral@localhost`. `pickup` (no task_id) returns per-agent mail _counts_ but no subjects. There is no way to get subject lines for the ghost, spectre, banshee, wraith, reaper, or raven mailboxes without dispatching a Raven to read them — a heavy operation when all the Admiral wants is a quick crew snapshot.

A lightweight "what's the crew thinking about?" call is missing. The Admiral often wants to know whether there's unread mail sitting in any agent's box — has a task completed and sent results to ghost? Is Raven waiting on something? — without pulling the full spawn list.

## What Changes

**`captain status`** gains a full broad mailbox skim across all 8 agent mailboxes (ghost, spectre, banshee, wraith, reaper, raven, captain, admiral), returning subject lines for each. Works even when dormant (no cron job running). Does not query the spawn list.

**`pickup` (crew-level, no task_id)** gains the same broad skim: per-agent subject lines added alongside the existing task list and mail counts. An optional `agent` parameter is added: when specified, `pickup` returns only that agent's mailbox subjects with no task list — a focused single-inbox read.

**`pickup` (task-specific)** is unchanged — stays targeted to that task's captain and admiral subjects.

A shared `_skim_all_mailboxes(crew_id)` helper is extracted and reused by both callers.

The mail-reading code is also refactored as part of this change: `read_mail_subjects.py` currently returns plain subject strings with no timestamp. It will be updated to also extract `Date:` headers and return `[{"subject": str, "received_at": str|None}]` per mailbox — the same shape as `_read_mail_subjects_archive`. This allows `_read_all_mail_subjects` (single exec, all 8 mailboxes) to replace the per-mailbox archive API calls, giving one consistent approach throughout the codebase.

## Capabilities

### Modified Capabilities

- `task-orchestration`: `pickup` (crew-level) gains `agent_subjects` field and optional `agent` filter parameter.
- `trn-captain-mail`: `captain status` response gains `agent_mail` field covering all 8 mailboxes.

## Impact

- `transport/container_scripts/read_mail_subjects.py` — add `Date:` header extraction; return `[{"subject": str, "received_at": str|None}]` per mailbox instead of plain strings.
- `transport/captain.py` — update `_read_all_mail_subjects` return type to `dict[str, list[dict]]`; add `_skim_all_mailboxes(podman, container)` thin wrapper; deprecate / replace `_read_mail_subjects_archive` call sites with the exec-based path.
- `transport/captain.py` — `captain status` handler: call `_skim_all_mailboxes`, add `agent_mail` to response, derive `captain_subjects`/`admiral_subjects` from skim result.
- `transport/server.py` — `pickup` tool: add `agent` parameter; call `_skim_all_mailboxes` when no task_id; add `agent_subjects` to crew-level response; when `agent` is specified, return single-inbox subjects only.
- `tests/unit/test_captain.py` and `tests/unit/test_server.py` — new tests for both response shapes, the agent filter, and the refactored mail reading.
- MCP tool schema: `pickup` gains optional `agent` string parameter.
