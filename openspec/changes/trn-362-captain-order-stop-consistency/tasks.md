# Tasks

## 1. Serialize stop with check-ins

- [ ] 1.1 Make Captain stop use the per-crew transition lock and verify it disables the schedule before returning without cancelling accepted Raven work.
- [ ] 1.2 Add barrier-controlled race tests for stop during a check-in and a check-in after stop returns; verify with `pytest tests/unit/test_captain_engine.py`.

## 2. Make order persistence failure-safe

- [ ] 2.1 Persist an inactive schedule candidate before mailbox delivery, activate it only after successful delivery, and compensate to a disabled state on activation failure; verify the order result never reports `ordered` on failure.
- [ ] 2.2 Add injected registry/mailbox failure tests for initial persistence, mailbox append, activation, and compensation; verify with `pytest tests/unit/test_captain_engine.py`.
