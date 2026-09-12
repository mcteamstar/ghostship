## 1. Fix _ensure_crew_running waiter race

- [x] 1.1 Locate `_ensure_crew_running` in `transport/lifecycle.py` — understand the Event + per-crew dict structure
- [x] 1.2 Add an outcome slot to the per-crew event entry: `_crew_restart_outcomes: dict[str, tuple[bool, Exception | None]]`
- [x] 1.3 In the leader block: use a `_outcome` local initialized to `(False, RuntimeError("leader failed"))` before the restart attempt; overwrite with `(True, None)` on success; on exception catch and store `(False, exc)` — then call `event.set()` after writing the outcome
- [x] 1.4 In waiter code after `event.wait()`: read the outcome and `raise` the stored exception if `success is False`
- [x] 1.5 Clean up the outcome entry after waiters have consumed it (or tie lifetime to the event's lifecycle)
- [x] 1.6 `python3 -m py_compile transport/lifecycle.py` — syntax clean

## 2. Recovery engine tests

- [x] 2.1 Add test: `_crew_api_with_recovery` — 503 on first call → phase0 retries → returns second response
- [x] 2.2 Add test: `_crew_api_with_recovery` — 401 stale cookie → phase1 refreshes cookie → retries → returns response
- [x] 2.3 Add test: `_crew_api_with_recovery` — connection error → phase2 restarts container → retries → returns response
- [x] 2.4 Add test: `_ensure_crew_running` — leader raises memory gate → waiter gets same exception (not stale-status proceed)
- [x] 2.5 Add test: `_ensure_crew_running` — leader raises gateway timeout → waiter propagates timeout error
- [x] 2.6 Run full unit suite — all pass
