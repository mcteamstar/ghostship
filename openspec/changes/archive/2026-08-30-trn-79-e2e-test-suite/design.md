## Context

`tests/e2e/` exists with a discoverable placeholder. `tests/run.sh --e2e` runs `python3 -m unittest discover -s tests/e2e`. The transport MCP tools are also available as a Python HTTP API — the e2e tests call the transport's REST/MCP endpoints directly with `httpx` (already in `transport/requirements.txt`).

## Goals / Non-Goals

**Goals:** Automate the manual smoke test as a repeatable suite. Skip cleanly when no transport is available.

**Non-Goals:** Test every MCP tool — focus on the core flow. Mock nothing — these are live tests. Add to CI by default (leave that as a follow-on once a test transport is provisioned).

## Decisions

### Skip on missing env var

**Decision:** Use `unittest.skipUnless(os.environ.get("GHOSTSHIP_E2E_URL"), "GHOSTSHIP_E2E_URL not set")` as a class decorator on every test class. The whole suite is a no-op when unset — safe for CI runs that don't have a transport.

### Direct HTTP, not MCP client

**Decision:** Call the transport's endpoints directly with `httpx` rather than wrapping an MCP client library. Two endpoint styles:
- **REST endpoints** (`/health`, `/version`) — plain `GET` requests
- **MCP tools** (`launch`, `nuke`, `crews`, `dispatch`, `pickup`, `supply`, `evac`) — `POST /mcp` with the standard MCP JSON-RPC envelope: `{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "<tool>", "arguments": {...}}, "id": 1}`

This keeps tests simple with no extra MCP client dependency. A small helper `_mcp_call(tool, **kwargs)` in the test file wraps the JSON-RPC boilerplate.

### Crew naming

**Decision:** Each test class uses a fixed `crew_id` prefixed with `e2e-` (e.g. `e2e-lifecycle`, `e2e-dispatch`). `setUp` nukes any stale crew with that name before creating a fresh one; `tearDown` nukes it after. This makes tests idempotent on re-run.

### Timeouts

Dispatch+pickup tests poll with a 5s interval up to 120s total — enough for a trivial task (`echo done`) without hanging indefinitely. Supply+evac uses a 30s timeout on the presigned URL fetch.

### Auth gate test

The auth gate test only runs if `GHOSTSHIP_API_KEY` is also set (skip if not). It verifies that a request without `Authorization` gets a 401.

## Risks / Trade-offs

- Tests create real containers — each takes ~30s to launch. Full suite is ~5 min.
- If a test's `tearDown` fails (e.g. network issue), the `e2e-*` crew is left running. Operators should be aware these test crews may need manual cleanup.
- Supply+evac test uploads a small in-memory payload — no large file handling tested here.
