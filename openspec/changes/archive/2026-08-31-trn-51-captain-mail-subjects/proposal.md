# TRN-51 — Captain mail subjects without waking the container

## Problem

`captain status` and `pickup` currently require the crew container to be running
to read mailbox subject lines — they use `podman exec` to run scripts inside the
container. For a stopped (idle) crew this wakes the container just to read metadata.

See `proposal.md - Why` for the original motivation.

## Key discovery (post TRN-81)

The Podman archive API (`GET /libpod/containers/{name}/archive?path=...`) works on
**stopped containers** — it reads directly from the container's overlay filesystem
without requiring the process to run. Tested on the academy VM: HTTP 200 returned
for `/var/mail/captain` on an exited container.

This means:
- `/var/mail/` (container writable layer) is accessible via archive API on stopped containers
- No volume changes needed — mailboxes stay where they are
- No worker sidecar needed for mail reads
- The same `container_archive_get` call works whether the container is running or stopped

The _worker sidecar (TRN-81) is still correct for git operations (bundle/diff) which
require a live git process. Plain file reads and mail reads use archive API directly.

## Scope

### Part 1 — Fix evac plain-file path (patch from TRN-81)

`_handle_file_get`'s stopped-crew branch currently routes plain file reads through the
worker sidecar unnecessarily. Replace `worker_read_file` with a direct
`container_archive_get` call — no `_ensure_crew_running`, no worker, no 200ms overhead.
Git bundle and diff operations keep the worker path.

### Part 2 — Captain status: live mail subjects from stopped crews

`captain status` uses `podman exec read_mail_subjects.py` today. Replace with
`container_archive_get` to read the Maildir tar, then parse subject lines from
RFC 5322 headers in `new/` and `cur/`. Works on both running and stopped containers
— no branching needed.

Add `admiral_subjects` and `captain_subjects` arrays to the `captain status` response:

```json
{
  "crew_id": "my-crew",
  "action": "status",
  "captain_mail": 2,
  "captain_subjects": ["trn-85 cleanup done", "trn-85 banshee review done"],
  "admiral_mail": 1,
  "admiral_subjects": ["SO1 complete -- trn-85 archived, cron paused"],
  ...
}
```

### Part 3 — Remove stale subjects from `pickup`

Once `captain status` returns live subjects directly, remove `admiral_subjects`,
`captain_subjects`, `admiral_mail`, `captain_mail` from the `pickup` response.
These are stale (reflect last Raven result, not current mailbox state) and overlap
with captain status. Breaking change — update `ghostship-command` skill and docs.

## Out of scope

- Message bodies
- Other mailboxes (raven, ghost, etc.) in captain status — admiral + captain only
- Changing where `/var/mail/` is stored (not needed)

## Files affected

| File | Change |
|:-----|:-------|
| `transport/files.py` | Part 1: replace `worker_read_file` with `container_archive_get` for plain files on stopped crews |
| `transport/captain.py` | Part 2: replace exec-based subject read with archive-based Maildir parse |
| `transport/server.py` | Part 2: add subjects to captain status response; Part 3: remove from pickup |
| `.claude-plugin/skills/ghostship-command/SKILL.md` | Part 3: remove pickup mail fields, add captain status mail guidance |
| `tests/unit/test_captain.py` | Tests for archive-based subject read |
| `tests/unit/test_files.py` | Update: plain file stopped-crew path now uses archive not worker |
