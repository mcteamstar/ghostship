## Context

See proposal.md — Why for motivation.

The KiroCrew gateway spawn API (`/api/spawn/{id}`) returns `elapsed` (seconds since task started) but no wall-clock timestamps. The transport has no persistent task state beyond what the gateway API returns, so `created_at` and `started_at` must be recorded by the transport itself at dispatch time. `completed_at` can be derived from `created_at + elapsed` when `done=true`, or from the time the transport first observes a done response.

Mail subject lines are currently plain strings returned by `_read_maildir_subjects_from_tar` and `_read_all_mail_subjects`. Maildir messages contain a `Date` header which can be parsed cheaply by Python's `email.utils.parsedate_to_datetime`.

`crews.json` already stores `created_at` per crew; it is returned in the `crews` tool response. `last_task_at` is a new field that needs to be written on dispatch.

## Goals / Non-Goals

**Goals:**
- Timestamps on task lifecycle events in `dispatch` and `pickup`.
- `received_at` on mail subjects everywhere they appear.
- `created_at` and `last_task_at` in the `crews` list.
- `last_checkin_at` in `captain status`.

**Non-Goals:**
- Persistent task history (tasks are not stored beyond what the gateway holds).
- Sub-second precision.
- Backfilling timestamps for tasks dispatched before this change.

## Decisions

**D1: Transport records task created_at in an in-memory dict at dispatch time**

The transport maintains a module-level `_task_timestamps: dict[str, dict]` keyed by `task_id`, storing `{"created_at": <iso>, "started_at": None, "completed_at": None}` at dispatch time. On the first `pickup` where `elapsed > 0`, `started_at` is derived as `created_at + (now - elapsed)`. On the first `pickup` where `done=True`, `completed_at` is set to `now`.

This is in-memory only — timestamps are lost on transport restart. Acceptable for the stated goal (recent session awareness) and avoids adding a persistence layer.

Alternatives considered:
- *Derive from gateway elapsed*: `created_at ≈ now - elapsed` is computable without storage, but is only available when elapsed > 0 (running tasks). A task that was dispatched and then checked while still queued has elapsed=0.
- *Store in crews.json*: more durable but adds complexity and write contention.

**D2: Parse Maildir Date headers in _read_maildir_subjects_from_tar**

`_read_maildir_subjects_from_tar` currently returns `list[str]` (subject lines). Change the return type to `list[dict]` — `{"subject": str, "received_at": str | None}`. Parse the `Date` header with `email.utils.parsedate_to_datetime`, convert to UTC ISO 8601. If absent or unparseable, `received_at = None`.

This is the single source of truth for mail subjects — all callers (`_read_all_mail_subjects`, `_read_mail_subjects_archive`) flow through it, so the shape change propagates automatically.

**D3: last_task_at written to crews.json at dispatch time**

At dispatch, after a successful `/api/spawn`, write `last_task_at = utcnow().isoformat()` into the crew's entry in `crews.json`. The `crews` tool already reads from that file, so no separate path is needed.

**D4: last_checkin_at stored in the standing-orders schedule entry**

Captain check-ins are Raven tasks dispatched by a schedule job. When the transport fires a scheduled check-in it can write `last_checkin_at` into the crew's schedule entry (already stored per-crew in the data dir). `captain status` reads this field and returns it.

## Risks / Trade-offs

- **In-memory timestamps lost on restart** → Acceptable. `created_at` reverts to null for old tasks after restart, but new tasks immediately have timestamps. Document this in the tool description.
- **subject shape change is breaking for callers that expected strings** → The change is additive at the JSON level (objects instead of strings), but any code that does `subject_list[i].upper()` would break. All current callers in the transport only display or pass through subjects — no string operations. External callers (MCP tool consumers) receive richer data.
- **Date header timezone handling** → `parsedate_to_datetime` returns timezone-aware datetimes. Converted to UTC with `.astimezone(timezone.utc).isoformat()`. Naive dates (no tz in header) treated as UTC with a warning log.
