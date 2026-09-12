## Why

`registry._find_batch_by_task_ids` uses exact set equality to match a batch. If a caller passes a subset of a batch's task IDs (e.g. because one task was lost mid-dispatch), the lookup never matches, the batch never reaches `complete`, and `pickup(task_ids=[...])` stalls forever. Discovered by the 0.4.0 independent review (quality).

## What Changes

Fix `_find_batch_by_task_ids` to match on subset: if all provided `task_ids` are members of any registered batch's task list, return that batch. Add unit tests covering exact match, subset match, and disjoint (no match).

## Capabilities

### Modified Capabilities

- `batch-dispatch`: the batch lookup requirement changes from exact-set to subset matching.

## Impact

- `transport/registry.py` — `_find_batch_by_task_ids` logic
- `tests/unit/test_registry.py` — new tests for match variants
