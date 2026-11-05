# Design

## Context

See proposal.md — Why for motivation.

The existing `TestRadarApiCrewAgents` class (line ~288) has a `_make_fake_httpx()` instance
method that constructs a `types.ModuleType` replacement for the `httpx` module, with a fake
`AsyncClient`, fake `RequestError`, and controlled `.get` return value. It then uses
`patch.object(server, "httpx", fake_httpx)` to swap out the module reference.

The skipped classes use a different pattern: they call `_get_httpx()` to import the real `httpx`
or `httpx2` package, construct a real `httpx.Response(...)`, and patch `httpx` with a
`unittest.mock.MagicMock`. This breaks when the `httpx` version in the test venv is not the
same as what `radar/server.py` imports (the `httpx`/`httpx2` naming mismatch).

The fix: adapt the two skipped classes to the same fake-module pattern, which requires no real
httpx import at all.

## Goals / Non-Goals

**Goals:**
- Both classes run without skip.
- All existing test assertions (`assertEqual(status, 200)`, `assertIn("crews", data)`, etc.) pass.
- No production code touched.

**Non-Goals:**
- Extracting `_make_fake_httpx` to a shared location (good housekeeping, but out of scope here;
  it can stay as a per-class method or a module-level helper).
- Adding new test cases beyond the existing ones.

## Decisions

**Adapt skipped classes to use `_make_fake_httpx` pattern.**

The `TestRadarApiCrewsSuccess` class needs a `_make_fake_httpx` that returns a fake response with
`status_code=200` and JSON-encoded payload content. The `TestRadarApiCrewsTransportDown` class
needs variants for `request_error=True` and `status_code=500`.

The existing `_make_fake_httpx` in `TestRadarApiCrewAgents` is an instance method. The two
classes need their own copy, or it can be promoted to a module-level function. Either works —
copying the method is simpler and avoids coupling the classes together.

**Add a `_call_handler` adapter per class.**

The skipped classes call `_call(server.app, scope)` directly (top-level ASGI call). This is
different from `TestRadarApiCrewAgents` which calls `server.api_crew_agents` directly. For
`/api/crews`, the handler is the `api_crews` function in `radar/server.py`. The simplest approach
is to route via the ASGI app (same as the existing class structure) with `patch.object(server, "httpx", fake_httpx)` wrapping the `_run` call.

## Risks / Trade-offs

**[Minimal risk] Only test plumbing changes.**
No production behavior changes. If the fake-module pattern breaks something, the tests fail
loudly (rather than being silently skipped).
