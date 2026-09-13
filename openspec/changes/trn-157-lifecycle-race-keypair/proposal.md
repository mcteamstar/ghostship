## Why

Two critical concurrency/safety findings in `transport/lifecycle.py`: a third concurrent caller to `_ensure_crew_running` can clear `_crew_restart_outcomes` for a running restart, causing legitimate waiters to see a spurious restart failure on a healthy crew (TRN-152 fixed two-caller races but a three-caller case remains). Separately, when `launch()` fails partway through `_finish_crew_setup`, `_cleanup_crew` may be skipped, leaving an orphaned `admiral-pubkey-{crew_id}` Podman secret; a subsequent launch of the same `crew_id` fails with a 409 conflict from Podman's secret namespace.

## What Changes

- **CR-1 — Generation counter for `_startup_events`**: Introduce a `_startup_generation: dict[str, int]` map (guarded by `_startup_events_lock`) that increments whenever a new leader is elected. Waiters capture the generation at `event.wait()` entry and verify it has not changed before reading `_crew_restart_outcomes`. A generation mismatch means a subsequent cycle has started; the waiter retries from the top of `_ensure_crew_running` rather than reading stale state. This closes the three-caller window without changing the two-caller logic already in place.
- **CR-2 — Ensure `_cleanup_crew` is always called on `_finish_crew_setup` failure**: Wrap `_finish_crew_setup` at its call sites in `server.py` (`launch()`) so that any exception or error-dict return triggers `_cleanup_crew` if it was not already called internally. Additionally, ensure `_finish_crew_setup` itself always calls `_cleanup_crew` before returning an error dict (it already calls it on the two gateway-timeout paths; add the call to the `cookie` mint failure path at line ~1790). This guarantees `admiral-pubkey-{crew_id}` is removed on every failed launch path.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-lifecycle`: The crew setup completion requirement ("all-or-nothing") currently says the system SHALL clean up the crew if any required step fails — but does not specify the mechanism for ensuring cleanup when `_finish_crew_setup` is called from `launch()`. Adding a requirement that the Admiral pubkey Podman secret is removed on every failed launch path (including partial failures inside `_finish_crew_setup`) and that no orphaned secrets survive a failed launch is a spec-level behavioral addition.
- `idle-and-recovery`: The restart serialization requirement (concurrent callers wait for the leader) does not address the case where a third caller clears `_crew_restart_outcomes` before an existing waiter reads it. Adding a requirement for generation-stable outcome reads closes this gap at the spec level.

## Impact

- `transport/lifecycle.py`: `_ensure_crew_running` (~line 552) — add `_startup_generation` dict and increment on leader election; waiter reads generation before and after `event.wait()` to detect a new cycle; `_finish_crew_setup` (~line 1790) — add `_cleanup_crew` call before the cookie mint failure return.
- `transport/server.py`: `launch()` (~line 2078) — ensure `_finish_crew_setup` error-dict returns trigger `_cleanup_crew` via a wrapper or explicit check.
- No API surface changes. No registry schema changes. No new dependencies.
