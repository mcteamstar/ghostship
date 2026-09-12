## 1. Fix _find_batch_by_task_ids

- [x] 1.1 In `transport/registry.py`, locate `_find_batch_by_task_ids`
- [x] 1.2 Replace `set(provided) == set(recorded)` with `set(provided) <= set(recorded)` (subset match)
- [x] 1.3 `python3 -m py_compile transport/registry.py` — syntax clean

## 2. Unit tests

- [x] 2.1 Add test: exact match — provided IDs == batch IDs → returns batch
- [x] 2.2 Add test: subset match — provided IDs ⊂ batch IDs → returns batch
- [x] 2.3 Add test: superset — provided IDs ⊃ batch IDs → returns None
- [x] 2.4 Add test: disjoint — no overlap → returns None
- [x] 2.5 Run full unit suite — all pass
