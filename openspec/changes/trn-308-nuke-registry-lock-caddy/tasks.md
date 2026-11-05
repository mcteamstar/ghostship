# Tasks

## 1. Fix nuke() lock contention

- [ ] 1.1 In `transport/tools.py` `nuke()`, split the second `with registry:` block: read
  `_ui_p = registry._reg["crews"].get(crew_id, {}).get("dashboard_port")`, clear batch records,
  and pop the crew entry inside the lock — then move the three Caddy/port calls
  (`_caddy_portal.deregister_crew`, `_dashboard_gate.release_port`, `_caddy_portal.release_port`)
  to execute after the `with registry:` block closes.
  Verify: `grep` confirms no `_caddy_portal.deregister_crew` call appears inside a `with registry:`
  block in `tools.py`.

## 2. Unit test

- [ ] 2.1 In `tests/unit/test_tools.py` (create the file if it does not yet exist), add a test
  `TestNukeLockOrder` that patches `_caddy_portal` with a `MagicMock`, calls `nuke()` on a
  stubbed crew with a `dashboard_port`, and asserts that `deregister_crew` was called **after**
  the registry entry was removed (i.e., the crew is absent from the registry when
  `deregister_crew` is invoked).
  Verify: `pytest tests/unit/test_tools.py::TestNukeLockOrder -v` passes.

## 3. Regression check

- [ ] 3.1 Run the full unit test suite and confirm no regressions: `pytest tests/unit/ -q`.

## Workflow follow-up

- Assimilate the change after the PR is merged.
