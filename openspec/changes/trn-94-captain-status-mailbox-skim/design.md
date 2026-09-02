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

**D1: Two mailbox reading approaches — archive API chosen for `received_at` consistency**

Two existing mechanisms read mailbox subjects:

1. **`_read_all_mail_subjects(podman, container)`** — single container exec (`read_mail_subjects.py`), all 8 mailboxes in one call, returns `dict[str, list[str]]` (plain strings). Requires running container. No `received_at`.

2. **`_read_mail_subjects_archive(podman, container, mailbox_path)`** — Podman archive API per mailbox, works on stopped containers, returns `list[dict{"subject": str, "received_at": str|None}]`. One call per mailbox.

The existing main specs (`trn-captain-mail`, `task-orchestration`) and the current pickup implementation both use the `{"subject": str, "received_at": str}` format. To stay consistent with the established contract, the broad skim must use `_read_mail_subjects_archive` — 8 archive API calls, one per mailbox. Each is fast (~10ms); total ~80ms for a running crew.

**`_skim_all_mailboxes(podman, container) -> dict[str, list[dict]]`** is a new helper in `transport/captain.py` that calls `_read_mail_subjects_archive` for each of the 8 mailboxes in `_ALL_MAIL_MAILBOXES`, returns empty list per mailbox on failure, and works on stopped containers (archive API doesn't require the process to run).

**D2: `captain status` response — add `agent_mail` field**

The `agent_mail` field is added to the captain status response dict. The existing `captain_subjects`, `admiral_subjects`, `captain_mail`, `admiral_mail` top-level fields are kept for backward compatibility — they are populated from the `_skim_all_mailboxes` result (captain and admiral entries from the dict), removing the current separate `_mail_count` calls for those two mailboxes.

**D3: `pickup` (crew-level) — add `agent_subjects` field**

When `pickup` is called without a `task_id` and without an `agent` filter, the response gains an `agent_subjects` field containing the full skim result. The existing `mail_summary` counts field is unchanged.

**D4: `pickup` — optional `agent` parameter**

A new optional `agent: str | None = None` parameter is added to the `pickup` MCP tool. When set to one of the six persona names, the handler returns only that mailbox's subjects and count — no task list. When set to an invalid name, an error is returned. The `agent` parameter is only honoured when `task_id` is None.

**D5: `.openspec.yaml` ticket field**

Set `ticket: TRN-94` in `.openspec.yaml`.

## Risks / Trade-offs

- **8 archive API calls per skim** — one `_read_mail_subjects_archive` call per mailbox. Each uses the Podman archive endpoint (~10ms each); total ~80ms. The alternative (single exec via `_read_all_mail_subjects`) is faster but returns plain strings without `received_at`, breaking the established response contract. The archive approach is consistent with how pickup already reads captain/admiral subjects today.
- **Backward compatibility** — `agent_mail` and `agent_subjects` are additive fields. No existing callers are broken.
