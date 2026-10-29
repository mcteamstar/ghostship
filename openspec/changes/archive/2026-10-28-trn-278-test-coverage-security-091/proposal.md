## Why

Critical security paths have zero unit test coverage: `transport/security.py` (589
lines — password hashing, brute-force throttle, session store) has never had a
dedicated test file, and `transport/files.py` HMAC sign/verify machinery is the sole
authorization guard on `/files/*` yet is completely untested. Confirmed by the
indy-0.9.1 review (ID 2da91f40); a phantom exclusion in `scripts/security_scan.py`
shows the `security.py` gap was anticipated but never delivered.

## What Changes

- Add `tests/unit/test_security.py` — dedicated tests for `transport/security.py`:
  `hash_password`/`verify_password` round-trip, `Throttle` window + concurrency,
  `SessionStore` issue/validate/revoke/expiry, `validate_str` bounds,
  `SecretRedactionFilter` exception path, `get_secret` env-var path.
- Add `tests/unit/test_files.py` — HMAC sign/verify round-trips, expired token,
  wrong signature, mode mismatch (GET token used on POST), path-traversal escapes
  in `_safe_workspace_path`.
- Add `tests/unit/test_container_scripts.py` — `inject_policy.py` sign_policy
  HMAC round-trip; `transfer_raw.py` extraction modes.
- Extend `tests/unit/test_dashboard.py` — `handle_auth` valid/expired/revoked
  session paths; `handle_logout_post` revocation.
- Add `tests/unit/test_openapi.py` — `_to_openapi_path`, `_default_tag`,
  `generate_schema` round-trip.
- Remove phantom exclusion for `test_trn70_security.py` from
  `scripts/security_scan.py` (line 76).

## Capabilities

### New Capabilities

- `transport/security-primitives-tests`: Unit tests for the core security
  primitives in `transport/security.py` — password hashing, brute-force throttle,
  session store, string validation, secret redaction, and CSP nonce generation.

### Modified Capabilities

- `transport-test-coverage`: Extends existing test coverage tracking to include
  `transport/files.py` HMAC machinery, `transport/openapi.py` schema generation,
  and `transport/container_scripts/` security-sensitive scripts.

- `transport/dashboard-session-auth`: `handle_auth` and `handle_logout_post` now
  have direct unit tests asserting correct 200/401 responses for valid, expired,
  and revoked sessions.

- `file-transfer-security`: HMAC token sign/verify paths, mode-mismatch rejection,
  and path-traversal guards in `_safe_workspace_path` now have direct unit tests.

## Impact

- `tests/unit/test_security.py` — new file (~150 lines)
- `tests/unit/test_files.py` — new file (~120 lines)
- `tests/unit/test_container_scripts.py` — new file (~60 lines)
- `tests/unit/test_dashboard.py` — extended (~50 new lines)
- `tests/unit/test_openapi.py` — new file (~40 lines)
- `scripts/security_scan.py` — remove line 76 phantom exclusion
- No production code changes.
