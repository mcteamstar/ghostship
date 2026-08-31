# Design: Captain mail subjects without waking the container

See `proposal.md` for motivation and scope.

## Context

The Podman archive API (`GET /libpod/containers/{name}/archive?path=...`) reads from a
container's merged overlay filesystem without requiring the process to be running.
Tested on the academy VM: HTTP 200 for `/var/mail/captain` on an exited container.

`/var/mail/` lives in the container's writable overlay layer — not on a named volume —
but the archive API reaches it regardless. This means the same `container_archive_get`
call works on both running and stopped containers, with no branching needed.

Current exec-based flow for mail reads:
```
_ensure_crew_running → container_exec(read_mail_subjects.py) → parse JSON
```
Requires: running container, gateway healthy, ~2–3s on wake.

New archive-based flow:
```
container_archive_get(container, "/var/mail/{mailbox}") → stream tar → parse RFC 5322 headers
```
Requires: container exists (stopped or running). No wake, no exec, no scripts.

## Goals / Non-Goals

**Goals:**
- `captain status` returns live subject lines from stopped crews without waking them
- Plain file evac on stopped crews uses archive API directly (no worker overhead)
- `pickup` cleaned of stale mail subject fields

**Non-Goals:**
- Message bodies in captain status
- All-mailbox subjects in captain status (admiral + captain only)
- Changing where `/var/mail/` is stored

## Decisions

### Decision 1: Archive API replaces exec for all mail reads

**Chosen:** `container_archive_get(container, "/var/mail/{mailbox}")` streams a Maildir
tar. Parse RFC 5322 `Subject:` headers from files in `new/` and `cur/`.

**Rejected:** Keep exec path for running containers, archive only for stopped.
The archive API works identically for both states — a single path is simpler,
eliminates the running/stopped branch entirely, and removes the dependency on
`read_mail_subjects.py` running inside the container.

**Rejected:** Worker sidecar for mail reads. `/var/mail/` is in the container's writable
layer, not on the workspace volume — the worker can't mount it. And archive API
is already simpler than the worker for this case.

### Decision 2: Parse Maildir headers in transport Python, not in a container script

**Chosen:** Stream the tar response, extract each file in `new/` and `cur/`,
parse `Subject:` from the RFC 5322 headers using Python's `email.parser` stdlib module.
No container-side script required.

**Rationale:** The transport already has `_TarMemberStream` for streaming tar members.
`email.parser` is stdlib, zero new dependencies. Keeps the logic transport-side where
it can be unit-tested without a container.

### Decision 3: Plain file evac on stopped crews — archive API, not worker

**Chosen:** Remove `worker_read_file` from `_handle_file_get`'s stopped-crew branch.
Replace with `container_archive_get(crew["container"], f"{ws}/{clean}")` directly —
the same call the running-crew path already makes, minus `_ensure_crew_running`.

**Rationale:** The worker sidecar was built to work around the assumption that archive
API needed a running container. That assumption was wrong. Git bundle/diff keep the
worker (they need a live git process). Plain files do not.

### Decision 4: `captain status` drops `_ensure_crew_running` for status action

**Chosen:** In `server.py`'s captain handler, branch on `action == "status"` before
calling `_ensure_crew_running`. Status reads only use archive API — no gateway needed.
Non-status actions (order, stop) still require a running container (gateway needed for
cron API calls).

### Decision 5: Remove stale mail fields from `pickup`

**Chosen:** Remove `admiral_subjects`, `captain_subjects`, `admiral_mail`,
`captain_mail` from the `pickup` response. `captain status` now provides these live.
Breaking change — bump skill file and mention in release notes.

**Rejected:** Keep both. Redundant and misleading since pickup fields are stale
(populated from last Raven result, not current mailbox state).

## Risks / Trade-offs

**[Risk] Archive tar for a mailbox with many messages could be large** → Mitigation:
subjects are read from headers only — `email.parser` reads just the header block before
the body, so parsing is O(message count) not O(message size). Cap at a reasonable
message count if needed (low priority).

**[Risk] Breaking change to pickup response** → Mitigation: document clearly in
release notes; update `ghostship-command` skill before shipping.

**[Risk] Archive API behaviour on a container being stopped mid-read** → Mitigation:
same risk exists today for running containers. The archive call is a single HTTP
request; if it fails, the caller gets a 500 and can retry. No worse than current.

## Migration Plan

1. Patch `_handle_file_get` stopped-crew plain-file path (archive replaces worker)
2. Add `_read_mail_subjects_archive(podman, container, mailboxes)` to `captain.py`
3. Update `captain status` handler to skip `_ensure_crew_running` and use archive reader
4. Add subjects to captain status response shape
5. Remove stale fields from pickup response
6. Update `ghostship-command` skill
7. Deploy — no data migration needed
