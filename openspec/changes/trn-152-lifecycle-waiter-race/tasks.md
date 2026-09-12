## 1. Fix _ensure_crew_running waiter race

- [ ] 1.1 Locate `_ensure_crew_running` in `transport/lifecycle.py` — understand the Event + per-crew dict structure
- [ ] 1.2 Add an outcome slot to the per-crew event entry: `_crew_restart_outcomes: dict[str, tuple[bool, Exception | None]]`
- [ ] 1.3 In the leader's `finally` block: write `(True, None)` on success, `(exc_type is None, exc)` on failure before calling `event.set()`
- [ ] 1.4 In waiter code after `event.wait()`: read the outcome and `raise` the stored exception if `success is False`
- [ ] 1.5 Clean up the outcome entry after waiters have consumed it (or tie lifetime to the event's lifecycle)
- [ ] 1.6 `python3 -m py_compile transport/lifecycle.py` — syntax clean

## 2. Recovery engine tests

- [ ] 2.1 Add test: `_crew_api_with_recovery` — 503 on first call → phase0 retries → returns second response
- [ ] 2.2 Add test: `_crew_api_with_recovery` — 401 stale cookie → phase1 refreshes cookie → retries → returns response
- [ ] 2.3 Add test: `_crew_api_with_recovery` — connection error → phase2 restarts container → retries → returns response
- [ ] 2.4 Add test: `_ensure_crew_running` — leader raises memory gate → waiter gets same exception (not stale-status proceed)
- [ ] 2.5 Add test: `_ensure_crew_running` — leader raises gateway timeout → waiter propagates timeout error
- [ ] 2.6 Run full unit suite — all pass
