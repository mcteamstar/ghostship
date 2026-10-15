## Why

`transport/auth.py` contains the transport's complete authentication and access-control surface — bearer API-key gating, transport-secret enforcement, rate limiting, session-cookie validation, and security-header injection — yet has no dedicated unit test file. Auth regressions in these classes are currently caught only indirectly by e2e tests, which are slow and require a running container environment. Adding a fast, isolated unit suite for `auth.py` closes this gap and ensures every auth path is verifiable without Podman.

## What Changes

- New test file `tests/unit/test_auth.py` covering all classes and helpers in `transport/auth.py`.
- Tests are pure unit tests: no Podman, no live HTTP server, no subprocess. ASGI scopes are constructed as plain dicts; middleware is exercised by calling `__call__` directly.
- The existing `tests/unit/conftest.py` stub infrastructure is reused; no new test dependencies are introduced.

## Capabilities

### New Capabilities

- `transport/auth-unit-tests`: Unit-test requirements for `transport/auth.py` — what each class and helper must do, expressed as testable scenarios covering authentication flows, session management, token validation, and access-control enforcement.

### Modified Capabilities

<!-- none — transport/auth.py behaviour is not changing; only test coverage is added -->

## Impact

- New file: `tests/unit/test_auth.py` (~400–600 lines).
- No changes to `transport/auth.py` or any production code.
- Test suite: `pytest tests/unit/test_auth.py` runs without Podman in any environment where `starlette` and `pytest` are available (same as existing unit tests).
