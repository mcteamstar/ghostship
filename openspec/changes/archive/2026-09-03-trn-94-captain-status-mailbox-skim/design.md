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

**D1: Refactor mail reading to one approach — enhanced exec script**

Currently three mechanisms exist for reading mailbox subjects, with inconsistent return shapes:

1. **`_read_all_mail_subjects`** — single exec, all 8 mailboxes, plain strings, running container only
2. **`_read_mail_subjects_archive`** — archive API, one mailbox per call, `{subject, received_at}`, works on stopped containers
3. **`_read_maildir_subjects_from_tar`** — underlying tar parser used by #2

The right consolidation: enhance `read_mail_subjects.py` to also extract `Date:` headers and return `[{"subject": str, "received_at": str|None}]` per mailbox. This gives the exec-based path the same shape as the archive path — enabling `_read_all_mail_subjects` to become the single canonical approach: one exec, all 8 mailboxes, full data including `received_at`.

After the refactor:
- `_read_all_mail_subjects` return type changes to `dict[str, list[dict]]`
- `_read_mail_subjects_archive` call sites in `pickup` and `captain status` are replaced with `_skim_all_mailboxes` (a thin wrapper over `_read_all_mail_subjects`)
- `_read_mail_subjects_archive` and `_read_maildir_subjects_from_tar` are kept for stopped-container evac (where exec is unavailable) but no longer used for routine subject reads

The skim on a stopped crew: `_read_mail_subjects_archive` is still needed when the container isn't running. `_skim_all_mailboxes` should detect the running state and fall back to archive API per-mailbox if the exec fails, returning empty lists as a last resort.

**D2: `captain status` response — add `agent_mail` field**

The `agent_mail` field is added to the captain status response dict. The existing `captain_subjects`, `admiral_subjects`, `captain_mail`, `admiral_mail` top-level fields are kept for backward compatibility — they are populated from the `_skim_all_mailboxes` result (captain and admiral entries from the dict), removing the current separate `_mail_count` calls for those two mailboxes.

**D3: `pickup` (crew-level) — add `agent_subjects` field**

When `pickup` is called without a `task_id` and without an `agent` filter, the response gains an `agent_subjects` field containing the full skim result. The existing `mail_summary` counts field is unchanged.

**D4: `pickup` — optional `agent` parameter**

A new optional `agent: str | None = None` parameter is added to the `pickup` MCP tool. When set to one of the six persona names, the handler returns only that mailbox's subjects and count — no task list. When set to an invalid name, an error is returned. The `agent` parameter is only honoured when `task_id` is None.

**D5: `.openspec.yaml` ticket field**

Set `ticket: TRN-94` in `.openspec.yaml`.

## Risks / Trade-offs

- **Single exec for running crews** — `_read_all_mail_subjects` (one exec, all 8 mailboxes) replaces 8 archive API calls for running containers. Significantly faster and simpler.
- **Stopped crew fallback** — `_skim_all_mailboxes` falls back to `_read_mail_subjects_archive` per-mailbox when the exec fails (container stopped). Returns empty lists as a last resort.
- **`read_mail_subjects.py` format change** — changing the script output from plain strings to `{subject, received_at}` dicts is a breaking change for any caller that expects the old format. All callers are in `transport/captain.py` and are updated as part of this change.
- **Backward compatibility** — `agent_mail` and `agent_subjects` are additive fields on the MCP responses. No existing callers are broken.
