# TRN-51 — Captain mail subjects without waking the container

## Problem

`captain status` currently requires the crew container to be running — it reads mail counts via `podman exec`. For a stopped (idle) crew, calling `captain status` wakes the container just to read mailbox metadata.

The Admiral should be able to check crew mail state — at minimum subject lines — without restarting a container that went idle. This is especially important for the common pattern of checking whether a crew's standing order produced results overnight.

Current state:

| What you get | How | Requires running container? |
|:---|:---|:---|
| Mail counts | `captain status` → `podman exec read_mail_counts.py` | **Yes** |
| Subject lines | `pickup` (no task_id) → last Raven result, stale | **No** (transport-side cache) |
| Live subject lines | Dispatch Raven, wait | **Yes** |

The `pickup` subjects are stale — they reflect what Raven last reported, not the current mailbox state. There is no way to get live subject lines without either waking the container or dispatching an agent.

## Prerequisite

**TRN-81 must land first.** TRN-81 investigates and implements `podman volume export` as a read path for stopped crews. Once the transport can read files from a stopped crew's volume without restarting the container, TRN-51 can use that path to read Maildir files directly.

## Proposed change

### Part 1 — Volume-direct Maildir read (depends on TRN-81)

Using the stopped-crew file read path from TRN-81, implement a transport-side Maildir subject reader that:

- Works on both running containers (via existing `podman exec read_mail_subjects.py`) and stopped containers (via volume export path from TRN-81)
- Reads `/var/mail/admiral` and `/var/mail/captain` subject lines
- Returns live results in both cases

### Part 2 — Update `captain status`

`captain status` uses the running-container path today. Update it to:

1. If container is running → use existing `podman exec` path (fast, no change)
2. If container is stopped → use the TRN-81 volume read path (no wake, no restart)

Response shape — add `admiral_subjects` and `captain_subjects` arrays to `captain status`:

```json
{
  "crew_id": "my-crew",
  "action": "status",
  "unread_mail": 2,
  "captain_subjects": ["trn-85 cleanup done", "trn-85 banshee review done"],
  "admiral_subjects": ["SO1 complete -- trn-85 archived, cron paused"],
  ...
}
```

### Part 3 — Remove stale subjects from `pickup`

Once `captain status` returns live subjects directly, remove `admiral_subjects`, `captain_subjects`, `admiral_mail`, `captain_mail` from the `pickup` response. These are redundant and misleading (stale). Breaking change — update `ghostship-command` skill and docs.

## Out of scope

- Message bodies (separate follow-on if ever needed)
- Other mailboxes (raven, ghost, etc.) — admiral + captain only

## Files

| File | Change |
|:-----|:-------|
| `transport/captain.py` | Add branching read path (exec vs volume) for subject lines |
| `transport/server.py` | Add `captain_subjects` / `admiral_subjects` to `captain status` response; remove from `pickup` |
| `transport/podman.py` | Extend with volume read helper from TRN-81 |
| `tests/unit/test_captain.py` | Tests for stopped-container subject read path |
| `.claude-plugin/skills/ghostship-command/SKILL.md` | Remove pickup mail fields, add captain status mail guidance |

## Dependency

Blocked on TRN-81.
