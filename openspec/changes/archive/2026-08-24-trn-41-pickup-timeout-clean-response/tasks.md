## Tasks

- [x] Add `GA_PICKUP_MAX_POLL_SECS` module-level constant to `transport/server.py` (default 30), alongside the other `GA_*` env var reads
- [x] In the `pickup` tool function, clamp `effective_timeout` to `min(max(0, timeout_secs), GA_PICKUP_MAX_POLL_SECS)` when `timeout_secs > 0` (leave `timeout_secs=0` path unchanged)
- [x] In `_pickup_single`: add `out["reason"] = "timeout"` before the `return out` when `remaining <= 0` and `done` is False
- [x] In `_pickup_list`: apply the same `reason: "timeout"` annotation when the poll cap fires
- [x] Add `GA_PICKUP_MAX_POLL_SECS` to `docs/configuration.md` with description, default (30), and a note explaining the MCP client read-timeout motivation
- [x] Add a test in `transport/test_transport.py`: `pickup` with `timeout_secs=60` returns `{"done": false, "reason": "timeout"}` when the internal cap (`GA_PICKUP_MAX_POLL_SECS=5`) fires before the task completes — verify no exception is raised and the response is a normal dict
