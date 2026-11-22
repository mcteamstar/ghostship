# Tasks

## 1. Keep restart results scoped to their cycle

- [x] 1.1 Replace separately overwritten per-crew restart outcomes with a cycle-scoped record captured by leader and waiters; verify existing startup serialization behavior with `pytest tests/unit/test_lifecycle.py`.
- [x] 1.2 Add deterministic tests where a new generation begins before an earlier waiter reads success or failure; verify both waiters receive only their captured generation's outcome with `pytest tests/unit/test_lifecycle.py`.
- [x] 1.3 Verify different crews can still restart concurrently and that the 150-second waiter timeout and early-failure propagation remain covered by `pytest tests/unit/test_lifecycle.py`.
