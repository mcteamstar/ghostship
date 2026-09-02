## 1. Shared helper

- [ ] 1.1 Add `_skim_all_mailboxes(podman, container) -> dict[str, list[dict]]` to `transport/captain.py` — calls `_read_mail_subjects_archive` for each of the 8 mailboxes in `_ALL_MAIL_MAILBOXES`; returns empty list per mailbox on failure; works on stopped containers
- [ ] 1.2 Unit tests: running crew returns all 8 keys; stopped crew returns 8 empty lists; one exec failure leaves other mailboxes intact

## 2. captain status

- [ ] 2.1 Call `_skim_all_mailboxes` in the `captain status` handler (`transport/captain.py`)
- [ ] 2.2 Add `agent_mail` field to the response dict
- [ ] 2.3 Populate existing `captain_subjects` / `admiral_subjects` / `captain_mail` / `admiral_mail` from the skim result (no duplicate exec calls)
- [ ] 2.4 Unit tests: `agent_mail` present in response; dormant captain still returns `agent_mail`; stopped crew returns empty lists

## 3. pickup — crew-level broad skim

- [ ] 3.1 Call `_skim_all_mailboxes` in `pickup` when `task_id` is None and `agent` is None
- [ ] 3.2 Add `agent_subjects` field to the crew-level pickup response
- [ ] 3.3 Unit tests: `agent_subjects` present in crew-level pickup; task-specific pickup is unchanged

## 4. pickup — agent filter

- [ ] 4.1 Add optional `agent: str | None = None` parameter to the `pickup` MCP tool signature and docstring
- [ ] 4.2 When `agent` is set and `task_id` is None: call `_read_mail_subjects` for that mailbox only; return `{"agent": str, "subjects": list, "mail": int}`; no task list
- [ ] 4.3 Validate `agent` against the six persona names (ghost, spectre, banshee, wraith, reaper, raven); return error for invalid values
- [ ] 4.4 Unit tests: agent filter returns single-inbox response; invalid agent returns error; agent filter ignored when task_id is set

## 5. .openspec.yaml

- [ ] 5.1 Set `ticket: TRN-94` in `.openspec.yaml`

## 6. Validation

- [ ] 6.1 Run `tests/run.sh --unit` — all tests pass
- [ ] 6.2 Run `openspec validate --specs` — 0 failures
