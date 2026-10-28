## 1. test_security.py — security primitives

- [x] 1.1 Create `tests/unit/test_security.py`. Confirm `freezegun` is in test
  dependencies (check `requirements-test.txt` or `pyproject.toml`).
- [x] 1.2 Add `hash_password`/`verify_password` round-trip tests: correct password
  → True, wrong password → False, empty string password.
- [x] 1.3 Add `Throttle` tests: lockout after `max_failures`, unlock after window
  expiry, reset on `record_success`.
- [x] 1.4 Add `SessionStore` tests using `freezegun` for time manipulation: issue
  → validate → revoke cycle; expired token rejected; revoked token rejected
  immediately.
- [x] 1.5 Add `validate_str` bounds tests: too long, contains disallowed chars,
  valid input passes.
- [x] 1.6 Add `SecretRedactionFilter` test: exception in redaction returns original
  message without crashing.
- [x] 1.7 Remove the phantom exclusion for `test_trn70_security.py` from
  `scripts/security_scan.py` (line 76).
- [x] 1.8 Run `pytest tests/unit/test_security.py` — all tests pass.

## 2. test_files.py — HMAC sign/verify

- [x] 2.1 Create `tests/unit/test_files.py`. Use `monkeypatch` to set
  `GA_FILE_SECRET` to a fixed test value before importing file functions.
- [x] 2.2 Add sign/verify round-trip tests: `_sign_file_url` + `_verify_file_token`
  for GET and PUT methods.
- [x] 2.3 Add tampered signature test: modify `sig` param → verification fails.
- [x] 2.4 Add expired token test: sign with past expiry → verification fails.
- [x] 2.5 Add mode mismatch test: GET token used on PUT → rejected.
- [x] 2.6 Add `_safe_workspace_path` path traversal tests: `../` sequences and
  absolute paths are rejected.
- [x] 2.7 Run `pytest tests/unit/test_files.py` — all tests pass.

## 3. test_container_scripts.py — container scripts

- [x] 3.1 Create `tests/unit/test_container_scripts.py`. Add
  `transport/container_scripts/` to `sys.path` in a module-level fixture.
- [x] 3.2 Add `inject_policy.py` sign_policy HMAC round-trip test.
- [x] 3.3 Add `transfer_raw.py` extraction mode tests (at least: normal extraction,
  path-traversal attempt rejected). Add Python 3.12 version guard for
  `filter="data"` behaviour.
- [x] 3.4 Run `pytest tests/unit/test_container_scripts.py` — all tests pass.

## 4. test_dashboard.py — handle_auth and handle_logout_post

- [x] 4.1 Extend `tests/unit/test_dashboard.py` with a `TestDashboardGateAuth`
  class.
- [x] 4.2 Add test: valid session → `handle_auth` returns 200.
- [x] 4.3 Add test: expired session → `handle_auth` returns 401.
- [x] 4.4 Add test: revoked session (after `handle_logout_post`) → `handle_auth`
  returns 401.
- [x] 4.5 Run `pytest tests/unit/test_dashboard.py` — all tests pass.

## 5. test_openapi.py — schema generation

- [x] 5.1 Create `tests/unit/test_openapi.py`.
- [x] 5.2 Add `_to_openapi_path` tests: path params, static segments.
- [x] 5.3 Add `_default_tag` tests: known and unknown paths.
- [x] 5.4 Add `generate_schema` round-trip: stub a minimal routes dict → returned
  schema has required OpenAPI 3.1 fields (`openapi`, `info`, `paths`).
- [x] 5.5 Run `pytest tests/unit/test_openapi.py` — all tests pass.

## 6. Verification

- [x] 6.1 Run full unit suite: `bash scripts/run.sh --unit` — all tests pass.
