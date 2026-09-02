## Context

Both `captain status` and crew-level `pickup` need the same broad mailbox skim — all 8 agent mailboxes, subjects only. The mechanism already exists: `_read_mail_subjects` in `transport/server.py` (or `transport/captain.py`) reads subject lines from a named mailbox via a container exec. The captain handler already calls it for `captain@localhost` and `admiral@localhost`. This change extends both call sites to cover all 8 mailboxes using a shared helper.

## Goals / Non-Goals

**Goals:**
- `captain status` returns all 8 mailbox subject lists.
- Crew-level `pickup` (no task_id) returns all 8 mailbox subject lists alongside the existing task list.
- `pickup` gains an optional `agent` filter parameter for single-inbox reads.
- Backward compatible — existing response fields unchanged.

**Non-Goals:**
- Message bodies (subjects only).
- Changing task-specific `pickup` behaviour.
- Removing the existing `captain_subjects` / `admiral_subjects` fields.

## Decisions

**D1: Shared `_skim_all_mailboxes(crew_id)` helper**

Extract a helper that calls `_read_mail_subjects` for each of the 8 mailboxes (ghost, spectre, banshee, wraith, reaper, raven, captain, admiral) and returns a dict keyed by mailbox name. Both `captain status` and crew-level `pickup` call this helper. If the container is stopped or an exec fails for a mailbox, that mailbox contributes an empty list rather than erroring the whole call.

The helper lives in `transport/server.py` alongside the existing mail-reading utilities.

**D2: `captain status` response — add `agent_mail` field**

The `agent_mail` field is added to the captain status response dict. The existing `captain_subjects`, `admiral_subjects`, `captain_mail`, `admiral_mail` top-level fields are kept for backward compatibility — they are populated from the same skim result (no extra exec calls).

**D3: `pickup` (crew-level) — add `agent_subjects` field**

When `pickup` is called without a `task_id` and without an `agent` filter, the response gains an `agent_subjects` field containing the full skim result. The existing `mail_summary` counts field is unchanged.

**D4: `pickup` — optional `agent` parameter**

A new optional `agent: str | None = None` parameter is added to the `pickup` MCP tool. When set to one of the six persona names, the handler returns only that mailbox's subjects and count — no task list. When set to an invalid name, an error is returned. The `agent` parameter is only honoured when `task_id` is None.

**D5: `.openspec.yaml` ticket field**

Set `ticket: TRN-94` in `.openspec.yaml`.

## Risks / Trade-offs

- **8 container execs per call** — each mailbox requires a container exec. For a stopped crew, all 8 fail fast (container not running) and return empty. For a running crew, 8 concurrent mailbox reads adds latency (~200ms total). Acceptable given the benefit.
- **Backward compatibility** — `agent_mail` and `agent_subjects` are additive fields. No existing callers are broken.
