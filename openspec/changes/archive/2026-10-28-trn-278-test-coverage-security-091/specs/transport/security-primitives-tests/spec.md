## Purpose

Unit tests for the core security primitives in `transport/security.py` — password
hashing, brute-force throttle, session store, string validation, secret redaction,
and CSP nonce generation. Previously this 589-line module had zero dedicated tests.

## ADDED Requirements

### Requirement: hash_password and verify_password are tested end-to-end

`tests/unit/test_security.py` SHALL include tests that call `hash_password` and
then `verify_password` on the result, asserting a correct password returns True and
an incorrect password returns False.

#### Scenario: Correct password verifies successfully
- **WHEN** `hash_password("secret")` is called and the result passed to `verify_password("secret", hash)`
- **THEN** `verify_password` returns True

#### Scenario: Wrong password fails verification
- **WHEN** `hash_password("secret")` is called and `verify_password("wrong", hash)` is called
- **THEN** `verify_password` returns False

### Requirement: Throttle enforces brute-force lockout window

`tests/unit/test_security.py` SHALL include tests for `Throttle` covering: lockout
after `max_failures` within the window, and successful unlock after the window expires.

#### Scenario: Throttle locks after max_failures
- **WHEN** `record_failure` is called `max_failures` times within the window
- **THEN** `is_locked` returns True

#### Scenario: Throttle unlocks after window expiry
- **WHEN** failures were recorded outside the current window
- **THEN** `is_locked` returns False

### Requirement: SessionStore issue/validate/revoke cycle is tested

`tests/unit/test_security.py` SHALL include tests for `SessionStore` covering:
issued token validates successfully; expired token returns invalid; revoked token
returns invalid immediately after revocation.

#### Scenario: Issued token validates
- **WHEN** `issue()` returns a token and `validate(token)` is called
- **THEN** `validate` returns a truthy session object

#### Scenario: Revoked token is rejected
- **WHEN** `revoke(token)` is called and then `validate(token)` is called
- **THEN** `validate` returns None or falsy

#### Scenario: Expired token is rejected
- **WHEN** a token is issued with a TTL of 1 second and `validate` is called after expiry
- **THEN** `validate` returns None or falsy

### Requirement: SecretRedactionFilter phantom exclusion is removed

`scripts/security_scan.py` SHALL NOT contain an exclusion for
`tests/unit/test_trn70_security.py`. The exclusion SHALL be removed once
`test_security.py` exists.

#### Scenario: security_scan.py no longer references a non-existent test file
- **WHEN** `scripts/security_scan.py` is read
- **THEN** the string `test_trn70_security.py` does not appear in it
