## Context

Six independent code quality fixes in `transport/server.py` and `tests/unit/test_transport.py`. None introduce new external behaviour; each corrects an existing defect or improves internal clarity. See proposal.md for motivation.

One item from the original TRN-56 ticket (/version auth) is **dropped**: `openspec/specs/mcp-server/spec.md` explicitly requires `GET /version` to be unauthenticated (`SHALL NOT require authentication`). The Banshee finding contradicts the spec intent, which is that version info is not sensitive enough to gate.

## Goals / Non-Goals

**Goals:**
- Fix fail-closed idle monitor (crew incorrectly stopped on transient API error)
- Extend captain mail HMAC to cover Subject header
- Extract magic container prefix strings to named constants
- Fix flaky `test_cron_branch` that fails at HH:59
- Verify `_startup_events` pruning on leader failure

**Non-Goals:**
- Adding `/version` auth (contradicts spec)
- Any external API or behaviour changes

## Decisions

**Fail-open idle monitor:** On exception from `/api/spawn` or `/api/crons`, `continue` (skip crew) rather than `pass` (fall through to stop). The existing `pass` comment says "keep fail-closed stop behavior" — that comment is wrong: stopping a crew whose activity state is unknown is the wrong default. The safe default is to leave it running and retry next cycle.

**HMAC over headers:** Include `Subject:` and `From:` in the signed payload by changing the HMAC input from `body.encode()` to `f"Subject:{subject}\nFrom:admiral@localhost\n\n{body}".encode()`. The `X-Admiral-Sig` header value format is unchanged (hex digest). Verification in `verify-admiral-sig` (shell script) must be updated to match.

**Magic strings as constants:** Three module-level constants: `CREW_CONTAINER_PREFIX = "gs-"`, `CREW_VOLUME_PREFIX = "gs-vol-"`, `CREW_HOME_VOLUME_PREFIX = "gs-home-"`. Replace all inline string literals. The guard checks in `nuke` become `container.startswith(CREW_CONTAINER_PREFIX)` etc.

**Flaky test fix:** `test_cron_branch` currently asserts `job["next_fire_at"] > now + 60`. At HH:59:01 croniter correctly returns the next top-of-hour tick (~59 s away), which is `< now + 60`. Fix: instead of asserting against `now + 60`, assert that `job["next_fire_at"]` equals the value croniter would compute for `"0 * * * *"` given the same reference time — or more simply, assert it is not the fallback `now + 60` value by checking `abs(job["next_fire_at"] - (now + 60)) > 1`.

**`_startup_events` pruning:** The `finally` block in the leader path already does `_startup_events.pop(crew_id, None)` and `event.set()`. Verify this is unconditional (it is — it's a `finally`) and add a test that confirms the event is cleaned up even when the leader raises.

## Risks / Trade-offs

**[Risk] HMAC change breaks existing signed messages** — any captain mailbox message signed with the old body-only HMAC will fail verification after this change. Mitigation: in-flight crews are the only affected case; Raven re-reads standing orders each cycle so the next Captain order write will use the new signature. No migration needed for stored messages.

**[Risk] `verify-admiral-sig` shell script must be updated in sync** — the shell script computes the expected HMAC to verify. If the script is not updated to match the new signed payload, all standing orders will fail verification. Mitigation: update `verify-admiral-sig` in the same commit and add a test that round-trips sign → verify.
