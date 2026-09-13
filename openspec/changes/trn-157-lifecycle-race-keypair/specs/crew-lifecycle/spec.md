# Crew Lifecycle — Delta Spec (TRN-157)

## Requirement: Crew setup completion is all-or-nothing (amended)

This delta amends the existing "Crew setup completion is all-or-nothing" requirement to add two specific behavioral guarantees:

### Guarantee 1: Admiral pubkey Podman secret removed on every failed launch path

When `launch()` fails at any point after `podman.secret_create(f"admiral-pubkey-{crew_id}", ...)` has been called, the transport SHALL remove the `admiral-pubkey-{crew_id}` Podman secret as part of cleanup. This includes:

- Gateway timeout failures inside `_finish_crew_setup` (all return-dict error paths)
- Cookie mint failure inside `_finish_crew_setup`
- Any exception propagating out of `_finish_crew_setup` to `launch()`'s outer `except` block

`_cleanup_crew` already handles secret removal (line ~1215 in `lifecycle.py`). The requirement is that `_cleanup_crew` is called on **every** `_finish_crew_setup` error-dict return path, not only on the two gateway-timeout paths currently handled.

#### Scenario: _finish_crew_setup returns an error dict — secret is removed

- **WHEN** `_finish_crew_setup` returns `{"error": ...}` for any reason
- **THEN** `_cleanup_crew` has been called before that return, removing the `admiral-pubkey-{crew_id}` Podman secret
- **AND** a subsequent `launch()` with the same `crew_id` does not receive a Podman 409 conflict on `secret_create`

#### Scenario: _finish_crew_setup raises an exception — secret is removed

- **WHEN** any exception escapes `_finish_crew_setup` and is caught by `launch()`'s outer `except` block
- **THEN** `_cleanup_crew` is called in that block, removing the secret

## Requirement: Concurrent restart outcome reads are generation-stable

The restart serialization mechanism (TRN-152) uses a per-crew `threading.Event` to wake waiters after the leader records an outcome. This requirement adds a generation counter to protect against a third concurrent caller that arrives after the leader has popped the event and before waiters have read their outcome.

The transport SHALL maintain a `_startup_generation: dict[str, int]` map (guarded by `_startup_events_lock`, with the same lifecycle as `_startup_events`) that records the current generation number for each crew. When a new leader is elected for `crew_id`, the generation counter for that crew SHALL be incremented (or initialized to 0 on first use). A waiter SHALL capture the generation before calling `event.wait()`. After `event.wait()` returns, the waiter SHALL re-read the generation under `_startup_events_lock`. If the generation has changed, a new restart cycle has started; the waiter SHALL NOT read `_crew_restart_outcomes` for the old cycle but instead SHALL treat the wait as a timeout (raise a RuntimeError indicating concurrent restart cycle confusion) or retry `_ensure_crew_running` from the top.

#### Scenario: Two waiters, leader fails — both see the failure

- **WHEN** two callers arrive after a leader has been elected for `crew_id`
- **AND** the leader's restart fails
- **THEN** both waiters read `success=False` from `_crew_restart_outcomes` and raise the stored exception
- This is the existing TRN-152 behavior; the generation counter SHALL NOT break it.

#### Scenario: Third caller arrives mid-cycle, pops the event before waiters read

- **GIVEN** callers A (leader) and B (waiter) are mid-restart for `crew_id`
- **WHEN** a third caller C arrives immediately after A fires the event and pops `_startup_events[crew_id]`, and C becomes the new leader for a fresh restart cycle
- **THEN** B, waking from `event.wait()`, observes that `_startup_generation[crew_id]` has changed from the value it captured before waiting
- **AND** B does NOT read `_crew_restart_outcomes` for A's cycle
- **AND** B raises a RuntimeError or retries, rather than proceeding against a crew that may or may not be running

#### Scenario: Normal two-caller case is unaffected

- **WHEN** exactly two callers arrive (leader + one waiter) and the leader succeeds
- **THEN** the waiter reads `success=True` from `_crew_restart_outcomes` and returns normally; the generation counter is incremented but does not change between the waiter's capture and its post-wait read
