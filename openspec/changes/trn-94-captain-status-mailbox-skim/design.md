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

Extract a helper that calls `_read_mail_subjects` (which already exists in `transport/captain.py`) passing all 8 mailbox names in one container exec — `read_mail_subjects.py` takes a JSON list of mailbox names and returns a dict in a single call. No per-mailbox exec loop needed. Both `captain status` and crew-level `pickup` call this helper. If the container is stopped or the exec fails, all mailboxes return empty lists rather than erroring the whole call.

The helper lives alongside the existing `_read_mail_subjects` in `transport/captain.py` (or is just a thin wrapper around it with a fixed mailbox set).

**D2: `captain status` response — add `agent_mail` field**

The `agent_mail` field is added to the captain status response dict. The existing `captain_subjects`, `admiral_subjects`, `captain_mail`, `admiral_mail` top-level fields are kept for backward compatibility — they are populated from the same skim result (no extra exec calls).

**D3: `pickup` (crew-level) — add `agent_subjects` field**

When `pickup` is called without a `task_id` and without an `agent` filter, the response gains an `agent_subjects` field containing the full skim result. The existing `mail_summary` counts field is unchanged.

**D4: `pickup` — optional `agent` parameter**

A new optional `agent: str | None = None` parameter is added to the `pickup` MCP tool. When set to one of the six persona names, the handler returns only that mailbox's subjects and count — no task list. When set to an invalid name, an error is returned. The `agent` parameter is only honoured when `task_id` is None.

**D5: `.openspec.yaml` ticket field**

Set `ticket: TRN-94` in `.openspec.yaml`.

## Risks / Trade-offs

- **One container exec per call** — `_read_mail_subjects` already takes a list of mailboxes and handles them all in a single `python3 read_mail_subjects.py` exec. The broad skim is one call regardless of mailbox count. For a stopped crew it fails fast and returns empty. Latency is the same as the current captain/admiral skim — no regression.
- **Backward compatibility** — `agent_mail` and `agent_subjects` are additive fields. No existing callers are broken.
