# TRN-51 — Captain mail bodies

## Problem

`captain status` currently returns mail counts and subject lines but not message bodies. To read the actual content of crew mail (Admiral standing orders, Raven reports, completion notices) you have to dispatch a Raven task inside the crew and wait for it to return the content — a full agent round-trip just to read your inbox.

The two-tier situation post-TRN-51 partial work:

| What you get today | How |
|:---|:---|
| Count of unread messages | Live, via `read_mail_counts.py` container script |
| Subject lines | Live, via `read_mail_subjects.py` container script |
| Message bodies | Dispatch Raven, wait for result |

## Proposed change

Add full message body reading to `captain status` using the same container-script pattern as counts and subjects. No new agent dispatch, no new containers — just one more `podman exec` call.

### Part 1 — `read_mail_bodies.py` container script

New file: `transport/container_scripts/read_mail_bodies.py`

Follows the same structure as `read_mail_subjects.py`. Accepts a JSON list of mailbox names, reads each Maildir (or mbox fallback), parses messages via the `email` stdlib module, and returns a JSON object:

```json
{
  "admiral": [
    {"subject": "TRN-85 parallel execution addendum", "from": "admiral@localhost", "body": "..."},
    {"subject": "Drive OpenSpec change ...", "from": "captain@localhost", "body": "..."}
  ],
  "captain": []
}
```

Each entry includes `subject`, `from`, and `body` (the decoded text payload, whitespace-normalised). Long bodies are truncated at a configurable limit (default 2000 chars) to keep the MCP response bounded.

### Part 2 — `_read_mail_bodies()` in `captain.py`

New function alongside `_read_all_mail_counts()` and `_read_all_mail_subjects()`:

```python
def _read_mail_bodies(
    podman: PodmanClient,
    container: str,
    mailboxes: list[str],
    max_body_chars: int = 2000,
) -> dict[str, list[dict[str, str]]]:
```

Calls the container script, deserialises the result, returns the structured dict.

### Part 3 — Update `captain status` response

`captain status` already has two code paths (dormant and active). Both currently return counts only. Update both to also call `_read_mail_bodies()` for the `admiral` and `captain` mailboxes and include the result:

```json
{
  "crew_id": "my-crew",
  "action": "status",
  "status": "active",
  "unread_mail": 2,
  "unread_admiral_mail": 1,
  "admiral_mail": [
    {"subject": "...", "from": "admiral@localhost", "body": "..."}
  ],
  "captain_mail": [
    {"subject": "...", "from": "raven@localhost", "body": "..."},
    {"subject": "...", "from": "raven@localhost", "body": "..."}
  ],
  ...
}
```

The existing `unread_mail` / `unread_admiral_mail` count fields are kept for backward compatibility. The new `admiral_mail` / `captain_mail` arrays are additive.

### Part 4 — Update MCP tool docstring

Update the `captain` tool's `action: status` description to mention that it now returns message bodies, not just counts.

### Out of scope for this change

- Removing `admiral_subjects` / `captain_subjects` from `pickup` (deferred — breaking change, needs its own PR and skill file updates)
- Mark-as-read / moving messages from `new/` to `cur/` (no change to mailbox state; reading is always non-destructive)
- Exposing other mailboxes (raven, ghost, etc.) via captain — admiral + captain only

## Why not in pickup?

`pickup` is task-focused. The Admiral calls it to check whether a Ghost finished, not to read crew mail. Putting mail bodies in `captain status` keeps the tool separation clean: captain owns admiral↔crew communication, pickup owns task state.

## Effort

Small. The container script is ~60 lines following the existing pattern. The `captain.py` function is ~20 lines. The `server.py` update is plumbing the new function into the two `captain status` return paths. Tests follow the same mock pattern as `TestReadMailCounts` / `TestReadMailSubjects`.

## Files

| File | Change |
|:-----|:-------|
| `transport/container_scripts/read_mail_bodies.py` | New |
| `transport/captain.py` | New `_read_mail_bodies()` function |
| `transport/server.py` | Update `captain status` to include mail bodies |
| `tests/unit/test_captain.py` | Tests for `_read_mail_bodies()` and updated `captain status` response |
| `crews/_base/Containerfile` | No change — scripts are already copied via `COPY container_scripts/ /scripts/` |
