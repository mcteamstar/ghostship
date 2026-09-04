## 1. Fix captain stop in server.py

- [ ] 1.1 In the `captain stop` block (`transport/server.py` around line 3346): move the registry update outside the `if standing_job.get("enabled", False)` guard so it always runs when `action == "stop"`
- [ ] 1.2 Change the gateway API failure path from `return {"error": ...}` to `logger.warning(...)` so execution falls through to the registry update — the gateway call is best-effort
- [ ] 1.3 Verify: if the gateway call fails, `captain stop` still returns a success response (not an error), and the registry is updated to `enabled: false`

## 2. Tests

- [ ] 2.1 Add unit test: `captain stop` when gateway cron is already `enabled: false` (e.g. Raven paused it) → registry is still updated to `enabled: false`
- [ ] 2.2 Add unit test: `captain stop` when gateway API call fails/returns error → registry is still updated to `enabled: false`, and no error is returned to the caller
- [ ] 2.3 Run `tests/run.sh --unit` — all tests pass
