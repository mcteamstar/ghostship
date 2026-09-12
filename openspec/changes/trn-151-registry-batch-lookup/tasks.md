## 1. Fix _find_batch_by_task_ids

- [ ] 1.1 In `transport/registry.py`, locate `_find_batch_by_task_ids`
- [ ] 1.2 Replace `set(provided) == set(recorded)` with `set(provided) <= set(recorded)` (subset match)
- [ ] 1.3 `python3 -m py_compile transport/registry.py` — syntax clean

## 2. Unit tests

- [ ] 2.1 Add test: exact match — provided IDs == batch IDs → returns batch
- [ ] 2.2 Add test: subset match — provided IDs ⊂ batch IDs → returns batch
- [ ] 2.3 Add test: superset — provided IDs ⊃ batch IDs → returns None
- [ ] 2.4 Add test: disjoint — no overlap → returns None
- [ ] 2.5 Run full unit suite — all pass
