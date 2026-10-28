## Context

The four code changes are small and independent. The captain_engine tests are the
largest piece — the module has no external dependencies beyond the crew registry and
a mail delivery helper, making it straightforward to test with lightweight fakes.

`transport/launcher.py:316` — `event.wait(timeout=45)` is a one-line change.

`transport/security.py` — `SessionStore._sweep()` is already implemented; it just
needs to be called from `revoke()` and/or `validate()`. `RateLimiter` comment is
a one-liner.

`transport/server.py` — `_ensure_running_locks` is a dict; the nuke path already
calls cleanup functions, so adding a `_ensure_running_locks.pop(crew_id, None)` is
a one-liner.

pytest-cov: `scripts/run.sh` invokes `pytest`; adding `--cov=transport
--cov-report=term-missing` to the unit test invocation is the minimal change.

See `proposal.md` for motivation.

## Goals / Non-Goals

**Goals:**
- `test_captain_engine.py` with direct tests for the four priority functions
- Waiter timeout raised to 150 s
- `SessionStore._sweep()` called in `revoke()`/`validate()`
- `_ensure_running_locks` cleaned up on nuke
- pytest-cov added to CI unit test invocation

**Non-Goals:**
- Full captain_engine coverage — minimum viable tests for the highest-risk paths
- Changing the captain_engine API or architecture

## Decisions

### D1: Captain engine tests use lightweight registry fakes

`captain_engine.py` functions take a registry dict and a podman client. Tests
create minimal in-memory dicts and a `FakePodmanClient` — no full transport
startup needed.

### D2: SessionStore._sweep() called in revoke()

Calling `_sweep()` in `revoke()` is the right place — revocation is the action
that most benefits from immediate pruning. `validate()` is on the hot path
(called every request); adding a sweep there adds latency. `revoke()` is called
only on logout.

### D3: pytest-cov in scripts/run.sh unit target only

Add `--cov=transport --cov-report=term-missing` to the `unit` target in
`scripts/run.sh`. Integration and e2e targets are unaffected. This avoids coverage
overhead on the heavier suites.

## Risks / Trade-offs

- Raising the waiter timeout to 150 s means failed restarts take longer to surface
  a 502 to the caller. Acceptable: the alternative (spurious 502 during a valid
  restart) is worse, and the 502 path still fires eventually.
- pytest-cov adds ~5-10 s to the unit test run. Acceptable overhead.
