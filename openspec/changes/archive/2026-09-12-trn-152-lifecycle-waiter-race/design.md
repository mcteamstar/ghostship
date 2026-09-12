## Context

`_ensure_crew_running` uses a per-crew `asyncio.Event` to serialise concurrent callers — one "leader" performs the restart while "waiters" block on `event.wait()`. The current pattern: leader runs, `finally: event.set()`, waiters wake and re-read registry status. The bug: if the leader's restart raises, `finally` still fires the Event with no failure record; waiters see stale "running" status and make API calls against a dead crew.

`_crew_api_with_recovery` and its three `_phaseN` helpers are 0 tests. They represent the most complex retry logic in the transport.

## Goals / Non-Goals

**Goals:**
- Leader records failure outcome before firing the Event
- Waiters propagate that failure rather than proceeding
- Unit tests for the recovery engine (all three phases)
- Tests covering the new waiter failure-propagation path

**Non-Goals:**
- Changing the one-leader-many-waiters model
- Adding retries to `_ensure_crew_running` itself

## Decisions

**D1 — Store outcome on Event via a companion slot**

`asyncio.Event` has no built-in result slot. Attach a `_outcome: tuple[bool, Exception | None]` to the per-crew event dict (already keyed by `crew_id`). Leader writes `(False, exc)` on failure, `(True, None)` on success, then calls `event.set()`. Waiter reads the outcome after `event.wait()` and re-raises on `(False, exc)`.

**D2 — Tests use mocked PodmanClient + httpx2 responses**

The three phase helpers all make HTTP calls via the PodmanClient. Tests mock at the `container_exec`/`_crew_api` level using `unittest.mock.patch`, matching the pattern established in `test_lifecycle.py`.

## Risks / Trade-offs

- The outcome slot on the event dict is a small API change to the internal event structure — no external callers.
- Phase tests require careful mocking of the recovery call chain; a thin helper to build mock response sequences will help readability.
