## Context

`transport/security.py` has a phantom exclusion in `scripts/security_scan.py` for
`test_trn70_security.py` confirming the gap was known and never filled. The existing
test suite uses `FakePodmanClient` and dependency injection (no module-level mocking)
— new tests must follow the same pattern.

`transport/files.py` HMAC functions (`_sign_file_url`, `_sign_upload_url`,
`_verify_file_token`, `_safe_workspace_path`) are pure functions — no Podman
dependency, straightforward to test directly. The HMAC key is sourced via
`security.get_secret("GA_FILE_SECRET", ...)` — tests should inject a fixed test key.

`transport/container_scripts/` scripts run inside crew containers; unit tests for
them must import and call the Python logic directly without a container.

`transport/openapi.py` `generate_schema` takes a dict of routes and returns an
OpenAPI 3.1 dict — no external dependencies, straightforward to test with a minimal
stub.

See `proposal.md` for motivation.

## Goals / Non-Goals

**Goals:**
- `test_security.py` covering `hash_password`/`verify_password`, `Throttle`,
  `SessionStore`, `validate_str`, `SecretRedactionFilter`
- `test_files.py` covering HMAC sign/verify, expiry, mode mismatch, path traversal
- `test_container_scripts.py` covering `inject_policy.py` sign_policy, `transfer_raw.py`
- `test_dashboard.py` extended with `handle_auth`/`handle_logout_post` paths
- `test_openapi.py` covering schema generation round-trip
- Remove phantom `test_trn70_security.py` exclusion from `security_scan.py`

**Non-Goals:**
- 100% line coverage — every test must guard a named failure mode
- E2E tests (separate concern)
- Testing production code changes (this change is tests-only)

## Decisions

### D1: Follow existing FakePodmanClient + DI pattern

All new tests use the `FakePodmanClient` from `tests/fakes.py` where Podman
interaction is needed, and inject dependencies via function arguments rather than
`unittest.mock.patch`. This matches the existing test style.

### D2: Inject a fixed HMAC key in file tests

`security.get_secret("GA_FILE_SECRET", ...)` is called at module load in
`transport/files.py`. Tests should set `os.environ["GA_FILE_SECRET"]` to a fixed
test value in a `pytest.fixture` with `monkeypatch`, or call the sign/verify
functions directly with a test key if the API permits it.

### D3: Import container scripts as Python modules

`inject_policy.py` and `transfer_raw.py` are plain Python files. Tests import them
directly (add `transport/container_scripts/` to `sys.path` in the test) and call
their functions — no subprocess, no container.

## Risks / Trade-offs

- `SessionStore` expiry tests require time manipulation — use `freezegun` or mock
  `time.time`. `freezegun` is already in the test dependencies; confirm before use.
- `transfer_raw.py` tarfile tests on Python < 3.12 may not exercise the `filter="data"`
  path (L-1 from the indy review) — add a version guard in the test.
