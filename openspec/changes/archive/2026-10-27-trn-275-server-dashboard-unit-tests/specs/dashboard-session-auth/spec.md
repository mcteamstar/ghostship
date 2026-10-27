## ADDED Requirements

### Requirement: Per-session CSRF token uniqueness

The transport SHALL generate a fresh CSRF token for each new dashboard session
rather than reusing a single process-wide token.

#### Scenario: Two sessions receive distinct CSRF tokens

- **WHEN** two separate dashboard sessions are initiated
- **THEN** each session's `gs_csrf` cookie value SHALL be distinct

#### Scenario: CSRF token changes after session expiry

- **WHEN** a session expires and a new session is initiated
- **THEN** the new session's `gs_csrf` cookie value SHALL differ from the expired session's value

### Requirement: CSRF token rejection for forged values

The dashboard login endpoint SHALL reject requests that present a CSRF token
not matching the session's issued token.

#### Scenario: Forged CSRF token returns 401

- **WHEN** `POST /dashboard/login` is called with a valid `gs_csrf` cookie but a mismatched `X-CSRF-Token` header (or vice versa)
- **THEN** the transport SHALL return HTTP 401 without evaluating the API key

#### Scenario: Absent CSRF token returns 401

- **WHEN** `POST /dashboard/login` is called with no `gs_csrf` cookie or no `X-CSRF-Token` header
- **THEN** the transport SHALL return HTTP 401

#### Scenario: Matching CSRF token proceeds to key evaluation

- **WHEN** `POST /dashboard/login` is called with a matching `gs_csrf` cookie and `X-CSRF-Token` header
- **THEN** the transport SHALL proceed to evaluate the submitted API key (and return 200 on success)

### Requirement: SameSite=Strict on gs_session cookie

The `gs_session` cookie SHALL carry `SameSite=Strict` to prevent cross-site
request forgery via authenticated sessions.

#### Scenario: gs_session cookie has SameSite=Strict

- **WHEN** a successful `POST /dashboard/login` issues a `gs_session` cookie
- **THEN** the `Set-Cookie` header SHALL include `SameSite=Strict`

### Requirement: Open-redirect protection validates relative paths

`_validate_next_url` SHALL reject any `next` parameter that could redirect the
browser to an external origin or execute arbitrary code, after NFKC
normalisation.

#### Scenario: Relative path passes validation

- **WHEN** `_validate_next_url` is called with `/crews/abc`
- **THEN** it returns `/crews/abc` unchanged

#### Scenario: Protocol-relative URL is rejected

- **WHEN** `_validate_next_url` is called with `//evil.com/steal`
- **THEN** it returns `/`

#### Scenario: Absolute URL is rejected

- **WHEN** `_validate_next_url` is called with `https://evil.com`
- **THEN** it returns `/`

#### Scenario: JavaScript URI is rejected

- **WHEN** `_validate_next_url` is called with `javascript:alert(1)`
- **THEN** it returns `/`

#### Scenario: NFKC-normalised lookalike is rejected

- **WHEN** `_validate_next_url` is called with a Unicode lookalike that normalises to `//evil.com`
- **THEN** it returns `/`

#### Scenario: Empty string returns slash

- **WHEN** `_validate_next_url` is called with an empty string
- **THEN** it returns `/`
