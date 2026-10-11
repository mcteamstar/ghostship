# Tasks

## 1. Implementation

- [x] 1.1 In `transport/monitors.py` `_idle_monitor`, add the captain schedule check (the `any()` block from design.md) immediately before the `/api/crons` HTTP request block. Call `_note_idle_skip(crew_id, "captain check-in scheduled")` and `_touch_crew(crew_id)` before `continue`. Verify: the code path is reachable by reading it — the condition fires when `type=="captain"`, `enabled==True` (or absent), and `next_fire_at < _NEVER_FIRE_AT`.

## 2. Tests

- [x] 2.1 In `tests/unit/test_monitors.py`, add a test: crew has an enabled captain schedule entry with `next_fire_at = time.time() + 300` and no active tasks or gateway crons → assert `container_stop` is NOT called. Verify: `tests/run.sh --unit` passes.
- [x] 2.2 Add a test: crew has a captain schedule entry with `enabled: False` → assert the captain check does NOT block idle-stop (the crew is still stopped if otherwise idle). Verify: test passes.
- [x] 2.3 Add a test: crew has a captain schedule entry with `next_fire_at = _NEVER_FIRE_AT` → assert the captain check does NOT block idle-stop. Verify: test passes.
- [x] 2.4 Add a test: crew has a captain schedule entry with `enabled: True` and `next_fire_at < _NEVER_FIRE_AT` AND an active spawn task → assert the crew is not stopped (both hold conditions are independent). Verify: test passes.

## Workflow follow-up

- Archive the change after tests pass and the PR is merged.
