## Why

Five low/medium code quality issues identified in the Banshee code review (2026-08-25, TRN-56). None are individually large enough to warrant separate changes but together they reduce correctness risk, improve maintainability, and fix a flaky test that causes intermittent CI failures.

## What Changes

- **`_idle_monitor` fail-open behaviour**: The exception handlers and unexpected-response paths on the `/api/spawn` and `/api/crons` checks could fall through to `stop`, meaning a transient API error (timeout, connection reset, or non-success response) causes the monitor to incorrectly stop a live crew. Change to fail-open: on an error, skip the crew for this cycle rather than proceeding to stop it.
- **`_format_captain_mail` HMAC scope**: The `X-Admiral-Sig` header is computed over the message body only. Subject and other headers are not signed, so a replay attacker could swap subjects without invalidating the signature. Extend the signed payload to include `Subject:` and `From:` headers.
- **Magic container prefix strings**: `"gs-"`, `"gs-vol-"`, `"gs-home-"` appear as bare string literals in multiple places across `nuke`, `_cleanup_crew`, and `_ensure_crew_running`. Extract to module-level constants (`CREW_CONTAINER_PREFIX`, `CREW_VOLUME_PREFIX`, `CREW_HOME_VOLUME_PREFIX`).
- **`_startup_events` not pruned on leader failure**: If the leader path in `_ensure_crew_running` raises before reaching the `finally` block's cleanup, the event remains in `_startup_events` indefinitely. The `finally` block already handles this — verify it's correct and add a test.
- **Flaky `test_cron_branch`**: The test asserts `job["next_fire_at"] > now + 60` where `now` is captured before calling `_advance_next_fire_at`. At HH:59:01 the next top-of-hour tick is only ~59 s away, so the assertion fails. Fix by anchoring the assertion to the croniter-computed value directly rather than a time-based threshold.
- **`/version` authentication remains unchanged**: The endpoint stays public because the authoritative `mcp-server` specification explicitly requires unauthenticated access; the original review suggestion to gate it is outside this change.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `idle-and-recovery`: The idle monitor's activity-check errors and unexpected responses now fail open (skip the crew rather than stopping it).

## Impact

- `transport/server.py`: `_idle_monitor`, `_format_captain_mail`, `nuke`, `_cleanup_crew`, `_ensure_crew_running`
- `tests/unit/test_transport.py`: `test_cron_branch`, fail-open activity-check tests, and the `_startup_events` pruning test
- No breaking API changes
