## 1. Task timestamps

- [ ] 1.1 Add module-level `_task_timestamps: dict[str, dict]` to `transport/server.py`
- [ ] 1.2 In `dispatch`, after a successful `/api/spawn`, record `{"created_at": utcnow, "started_at": None, "completed_at": None}` in `_task_timestamps[task_id]`; include `created_at` in the dispatch response
- [ ] 1.3 In `_pickup_single`, populate `started_at` (once, when `elapsed > 0`) and `completed_at` (once, when `done=True`) from `_task_timestamps`; include all three fields in the pickup response (`null` when not yet set)
- [ ] 1.4 In `_pickup_list`, include `created_at`, `started_at`, `completed_at` in each task entry from `_task_timestamps` (null if not present — task was dispatched before this change or transport restarted)
- [ ] 1.5 Add unit tests: dispatch response includes `created_at`; pickup running task has `started_at` non-null and `completed_at` null; pickup done task has all three set; list entries include timestamp fields

## 2. Mail subject timestamps

- [ ] 2.1 Change `_read_maildir_subjects_from_tar` return type from `list[str]` to `list[dict]` — each entry `{"subject": str, "received_at": str | None}`
- [ ] 2.2 Parse the `Date` header from each Maildir message using `email.utils.parsedate_to_datetime`; convert to UTC ISO 8601; set `received_at = None` on missing or unparseable headers
- [ ] 2.3 Update all callers of `_read_maildir_subjects_from_tar` and `_read_all_mail_subjects` that assumed `list[str]` — confirm none do string operations on subjects (only display/pass through)
- [ ] 2.4 Update `_read_mail_subjects_archive` to return the same `list[dict]` shape
- [ ] 2.5 Add unit tests: subject with valid Date header returns correct `received_at`; subject with no Date header returns `received_at = null`; existing pickup/captain-status response shape tests updated

## 3. Crew list timestamps

- [ ] 3.1 In `dispatch`, after a successful spawn, write `last_task_at = utcnow().isoformat()` into the crew's entry in `crews.json`
- [ ] 3.2 Confirm `crews` tool already returns `created_at` from the registry (it does — server.py:1672); add `last_task_at` to the returned entry (null if not present)
- [ ] 3.3 Add unit tests: `crews` response includes `last_task_at` after a dispatch; `last_task_at` is null for a crew with no dispatches

## 4. Captain last_checkin_at

- [ ] 4.1 When the transport fires a captain check-in (schedule job tick), write `last_checkin_at = utcnow().isoformat()` to the crew's schedule entry in the data dir
- [ ] 4.2 In `captain status`, read `last_checkin_at` from the schedule entry and include it in the response (null if no check-in has fired)
- [ ] 4.3 Add unit tests: `captain status` includes `last_checkin_at` after a check-in fires; null before any check-in

## 5. Spec sync and validation

- [ ] 5.1 Merge delta specs into main specs: `task-orchestration`, `trn-captain-mail`, `crew-lifecycle`
- [ ] 5.2 Create main specs: `task-timestamps/spec.md`, `mail-timestamps/spec.md`
- [ ] 5.3 Run `openspec validate` and confirm no errors
