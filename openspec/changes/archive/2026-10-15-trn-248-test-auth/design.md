## Context

`transport/auth.py` (32 KB, ~800 lines) defines five public classes and three top-level helpers that compose into the transport's ASGI middleware stack:

```
HTTP request
  └─ TransportSecretMiddleware   (X-Transport-Token gate)
       └─ RateLimitMiddleware    (sliding-window per-endpoint)
            └─ BearerAuthMiddleware   (API-key + route dispatch)
                 └─ SecurityHeadersMiddleware  (CSP, HSTS, HTTPS redirect)
                      └─ downstream app (MCP / file app)
```

Helper functions: `_parse_bearer_token`, `_parse_rate_limit_var`, `_request_source`, `_build_rate_limiters`.

The existing unit test suite (`tests/unit/`) covers `config.py`, `login.py`, `registry.py`, and `lifecycle.py` (sentinel monitor). There is no `test_auth.py`. The project's unit test pattern (established in `test_login.py` and `conftest.py`) uses:
- Plain `unittest.TestCase` classes.
- ASGI scopes as plain `dict` objects (no live server needed).
- `tests/fakes.py` for external deps; no `unittest.mock.Mock()` unless unavoidable.
- The `_install_transport_stubs()` shim from `conftest.py` handles missing httpx/starlette at import time.

See proposal.md for motivation.

## Goals / Non-Goals

**Goals**: Cover all behaviors in the spec (`transport/auth-unit-tests/spec.md`) — every class, every helper, all error paths — without requiring Podman, a live server, or the full starlette runtime.

**Non-goals**: End-to-end coverage of the full middleware stack wired together; integration with `server.py`'s route table; testing `security.py` classes (they have separate coverage via `test_sentinel.py` and the existing session tests).

## Decisions

### 1. ASGI scope dicts, not Starlette TestClient

Options considered:
- **A. Use Starlette `TestClient`**: requires the full starlette runtime and a complete app; middleware constructor args are wired to `server.py` constants, making isolation hard.
- **B. Construct minimal ASGI scope dicts and invoke `__call__` directly** (chosen): each middleware is constructed in isolation with injected arguments; `scope`, `receive`, and `send` are minimal lambdas or lists. Consistent with how `transport-test-coverage` spec tests other ASGI middleware (see `test_login.py` pattern).

Rationale: no extra dependencies, faster, and the unit under test is the middleware's logic, not Starlette's routing.

### 2. Sync send/receive helpers over asyncio mocking

Each test constructs a `send_messages = []` list and an `async def collect_send(msg)` coroutine that appends to it. `receive` is an async lambda returning a minimal body event. This avoids any asyncio mock library dependency and is readable.

### 3. One TestCase class per class/helper under test

File structure:
```
tests/unit/test_auth.py
  TestParseBearerToken
  TestParseRateLimitVar
  TestBuildRateLimiters
  TestRequestSource
  TestTransportSecretMiddleware
  TestRateLimitMiddleware
  TestBearerAuthMiddleware
  TestSecurityHeadersMiddleware
```

Each class is independently importable (no shared state between classes). Per the project convention, no pytest fixtures inside `unittest.TestCase` classes — setUp/tearDown is used for per-test state.

### 4. Import shimming via existing conftest

`tests/unit/conftest.py` already calls `_install_transport_stubs()` at module load time, which installs the httpx/starlette/mcp stubs. `test_auth.py` imports `from transport import auth as _auth` (the local dev path) and relies on these stubs being present. No changes to `conftest.py` are needed.

### 5. Rate-limiter state reset between tests

`RateLimiter` (from `transport/security.py`) holds in-memory sliding-window state. Each `TestRateLimitMiddleware` test creates a fresh limiter instance with a short window, so no per-test cleanup is needed for the limiter itself.

### 6. Env var isolation

Tests that exercise env-var-sensitive helpers (`_parse_rate_limit_var`, `_build_rate_limiters`, `SecurityHeadersMiddleware`) use `unittest.mock.patch.dict(os.environ, {...}, clear=True)` to isolate env state.

## Risks / Trade-offs

- [ASGI scope construction is manual] → mitigation: a shared `_make_scope(method, path, headers)` helper at the top of the test file reduces boilerplate and is the single place to update if ASGI scope keys change.
- [starlette stub may not perfectly replicate `Request` behavior] → mitigation: `BearerAuthMiddleware` constructs `Request(scope, receive)` internally; if the stub's `Request` diverges, tests will fail loudly rather than silently pass. Acceptable risk for unit scope.
- [hmac.compare_digest behavior cannot be "asserted" directly without patching] → mitigation: instead of asserting the implementation detail, tests assert the behavioral consequence: wrong-token returns 401 regardless of the comparison approach. A static grep test (separate) can assert that `compare_digest` appears in the source.

## Migration Plan

1. Ghost implements `tests/unit/test_auth.py` from the spec and tasks.
2. Run `pytest tests/unit/test_auth.py -v` to confirm all tests pass.
3. No production code changes; no migration or rollback required.

## Open Questions

None — the scope is bounded to a new test file with no production code changes.
