## 1. Refactor mail reading

- [x] 1.1 Update `transport/container_scripts/read_mail_subjects.py` — extract `Date:` header alongside `Subject:`; return `[{"subject": str, "received_at": str|None}]` per mailbox instead of plain strings
- [x] 1.2 Update `_read_all_mail_subjects` in `transport/captain.py` — update return type annotation to `dict[str, list[dict]]`; update the JSON parse logic to handle the new dict format
- [x] 1.3 Add `_skim_all_mailboxes(podman, container) -> dict[str, list[dict]]` to `transport/captain.py` — calls `_read_all_mail_subjects` for the happy path (running container); falls back to `_read_mail_subjects_archive` per-mailbox if exec fails; returns empty lists as last resort
- [x] 1.4 Replace all `_read_mail_subjects_archive` call sites in `pickup` (`transport/server.py`) with `_skim_all_mailboxes` or direct `_read_all_mail_subjects` calls
- [x] 1.5 Unit tests: `read_mail_subjects.py` returns `{subject, received_at}` dicts; `_read_all_mail_subjects` returns new shape; fallback to archive on exec failure

## 2. Shared helper (now thin wrapper over refactored _read_all_mail_subjects)

- [x] 2.1 `_skim_all_mailboxes` implemented in task 1.3 above — this section tracks integration
- [x] 2.2 Unit tests: running crew returns all 8 keys with `{subject, received_at}` dicts; stopped crew returns 8 empty lists; one exec failure triggers per-mailbox archive fallback

## 2. captain status

- [x] 2.1 Call `_skim_all_mailboxes` in the `captain status` handler (`transport/captain.py`)
- [x] 2.2 Add `agent_mail` field to the response dict
- [x] 2.3 Populate existing `captain_subjects` / `admiral_subjects` / `captain_mail` / `admiral_mail` from the skim result (no duplicate exec calls)
- [x] 2.4 Unit tests: `agent_mail` present in response; dormant captain still returns `agent_mail`; stopped crew returns empty lists

## 3. pickup — crew-level broad skim

- [x] 3.1 Call `_skim_all_mailboxes` in `pickup` when `task_id` is None and `agent` is None
- [x] 3.2 Add `agent_subjects` field to the crew-level pickup response
- [x] 3.3 Unit tests: `agent_subjects` present in crew-level pickup; task-specific pickup is unchanged

## 4. pickup — agent filter

- [x] 4.1 Add optional `agent: str | None = None` parameter to the `pickup` MCP tool signature and docstring
- [x] 4.2 When `agent` is set and `task_id` is None: call `_read_mail_subjects` for that mailbox only; return `{"agent": str, "subjects": list, "mail": int}`; no task list
- [x] 4.3 Validate `agent` against the six persona names (ghost, spectre, banshee, wraith, reaper, raven); return error for invalid values
- [x] 4.4 Unit tests: agent filter returns single-inbox response; invalid agent returns error; agent filter ignored when task_id is set

## 5. .openspec.yaml

- [x] 5.1 Set `ticket: TRN-94` in `.openspec.yaml`

## 6. Validation

- [x] 6.1 Run `tests/run.sh --unit` — all tests pass
- [x] 6.2 Run `openspec validate --specs` — 0 failures
