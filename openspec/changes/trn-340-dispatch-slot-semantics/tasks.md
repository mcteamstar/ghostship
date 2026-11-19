# Tasks

## 1. Reconcile the dispatch contract

- [ ] 1.1 Update the Task dispatch spec requirement and scenarios to match enrollment-based defaults; verify the `slot=True` warning/fallback against `transport/lifecycle.py` and verify the boolean-or-null dispatch tool input contract.
- [ ] 1.2 Update README, architecture, configuration, and MCP tool descriptions to remove bridge and arbitrary slot guidance; explain the existing `slot=True` fallback and verify examples use only supported values. Do not change runtime behavior.
- [ ] 1.3 Add or update tests for enrolled default, unenrolled default, explicit headless, and the existing `slot=True` warning/fallback; run focused dispatch tests. Do not add runtime rejection behavior.

## 2. Verify docs and spec consistency

- [ ] 2.1 Search active docs/specs for bridge slots, per-task slot, `slot=True`, and dashboard-port-derived slot claims; verify no contradictory active guidance remains before syncing the delta.
