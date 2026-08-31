## 1. Plain file evac — replace worker with archive API

- [x] 1.1 In `_handle_file_get`, replace the `worker_read_file` call in the stopped-crew branch with `container_archive_get(crew["container"], f"{ws}/{clean}")` — same call the running path uses, minus `_ensure_crew_running`
- [x] 1.2 Remove the `worker_read_file` import/call from the stopped-crew plain-file path (keep `worker_git_bundle` and `worker_git_diff` for git ops)
- [x] 1.3 Update `test_files.py` unit tests: stopped-crew plain file test now expects archive API call, not worker

## 2. Transport-side Maildir subject reader

- [x] 2.1 Add `_read_maildir_subjects_from_tar(tar_bytes_or_stream) -> list[str]` to `captain.py` — iterates tar members in `new/` and `cur/`, parses `Subject:` header using `email.parser`, returns subject strings
- [x] 2.2 Add `_read_mail_subjects_archive(podman, container, mailbox_path) -> list[str]` to `captain.py` — calls `container_archive_get(container, mailbox_path)`, passes result to `_read_maildir_subjects_from_tar`
- [x] 2.3 Unit test `_read_maildir_subjects_from_tar` with synthetic tar bytes containing Maildir files with known subjects

## 3. Captain status — drop _ensure_crew_running, add subjects

- [x] 3.1 In the `captain status` handler in `server.py`, branch before `_ensure_crew_running`: if `action == "status"`, skip it and use `container_archive_get` via `_read_mail_subjects_archive` directly
- [x] 3.2 Add `captain_subjects` and `admiral_subjects` arrays to the captain status response (all status paths: dormant, active, and no-job)
- [x] 3.3 Add `captain_mail` and `admiral_mail` counts to status response (use existing `_mail_count` or derive from archive read)
- [x] 3.4 Verify stopped-crew `captain status` call does not start the container

## 4. Remove stale mail fields from pickup

- [x] 4.1 Remove `admiral_subjects`, `captain_subjects`, `admiral_mail`, `captain_mail` from the `pickup` response in `server.py` (both the task-specific and crew-wide paths)
- [x] 4.2 Update `ghostship-command` skill (`SKILL.md`) to remove references to pickup mail fields and add guidance on using `captain status` for live mail subjects
- [x] 4.3 Update any unit/e2e tests that assert on pickup mail fields

## 5. Tests

- [x] 5.1 Unit test captain status on stopped crew: mock `container_is_running` → False, mock `container_archive_get`, assert subjects returned without `_ensure_crew_running` called
- [x] 5.2 Unit test captain status on running crew: assert subjects still returned correctly
- [x] 5.3 E2e smoke test: call `captain status` on a stopped crew on the academy VM, assert HTTP 200 and subjects array present, assert crew container remains stopped
