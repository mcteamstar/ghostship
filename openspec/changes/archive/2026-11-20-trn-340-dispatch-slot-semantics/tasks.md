# Tasks

## 1. Reconcile the dispatch contract

- [x] 1.1 Update the Task dispatch and Batch dispatch spec requirements and scenarios to match enrollment-based defaults; verify the `slot=True` warning/fallback against `transport/lifecycle.py` and verify the boolean-or-null dispatch tool input contract.
- [x] 1.2 Update README, architecture, configuration, and MCP tool descriptions to remove bridge and arbitrary slot guidance; explain the existing `slot=True` fallback and verify examples use only supported values. Do not change runtime behavior.
- [x] 1.3 Add or update single and batch dispatch tests for enrolled defaults, unenrolled defaults, explicit headless, and the existing `slot=True` warning/fallback; run focused dispatch tests. Do not add runtime rejection behavior.

## 2. Verify docs and spec consistency

- [x] 2.1 Search docs and active specs for bridge slots, per-task slot, `slot=True`, and dashboard-port-derived slot claims. Confirm remaining legacy claims are only in the Task dispatch and Batch dispatch requirements superseded by this delta; sync will replace those requirements. Clarify the active crew-lifecycle heading to describe the warning and fallback accurately.
