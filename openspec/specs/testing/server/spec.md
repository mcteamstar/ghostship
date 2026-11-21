# testing/server Specification

## Purpose

Defines verification coverage for server behavior.

## Requirements

### Requirement: _ssl_context_factory test coverage

The test suite SHALL exercise `_ssl_context_factory` (the direct-TLS path via `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE`) to verify TLS version floor and file-path gating.

#### Scenario: TLS disabled — no cert/key configured
- **WHEN** `GA_TLS_CERTFILE` and `GA_TLS_KEYFILE` are not set
- **THEN** no `_ssl_context_factory` is registered on the uvicorn kwargs

#### Scenario: TLS enabled — valid cert and key files
- **WHEN** `GA_TLS_CERTFILE` and `GA_TLS_KEYFILE` are both set to readable files
- **THEN** `_ssl_context_factory` is registered and the returned context enforces TLS 1.2 as minimum

#### Scenario: TLS enabled — missing cert file raises
- **WHEN** `GA_TLS_CERTFILE` points to a non-existent file
- **THEN** `_ssl_context_factory` raises an appropriate error at startup

### Requirement: TransportSecretMiddleware and _load_transport_secret test coverage

The test suite SHALL exercise `TransportSecretMiddleware` and `_load_transport_secret`, covering the configured and unconfigured paths.

#### Scenario: Secret not configured — requests pass through
- **WHEN** no transport secret is configured (`GA_TRANSPORT_SECRET` absent / empty)
- **THEN** all requests pass through `TransportSecretMiddleware` without a 401

#### Scenario: Secret configured — correct header passes
- **WHEN** a transport secret is configured AND a request carries the correct `X-Transport-Token` value
- **THEN** the request passes through

#### Scenario: Secret configured — wrong header returns 401
- **WHEN** a transport secret is configured AND a request carries an incorrect `X-Transport-Token`
- **THEN** `TransportSecretMiddleware` returns 401

#### Scenario: Secret configured — missing header returns 401
- **WHEN** a transport secret is configured AND a request has no `X-Transport-Token` header
- **THEN** `TransportSecretMiddleware` returns 401

#### Scenario: Constant-time comparison used
- **WHEN** `TransportSecretMiddleware` validates the token
- **THEN** `hmac.compare_digest` (or equivalent constant-time compare) is used, not `==`

### Requirement: server.py pure utility function test coverage

The test suite SHALL exercise the pure utility functions in `transport/server.py`
as unit tests with no I/O, no live server, and no Podman dependency.

#### Scenario: _extract_crew_proxy_parts parses valid proxy path

- **WHEN** `_extract_crew_proxy_parts` is called with a path matching the crew proxy pattern (e.g. `/crews/abc/ui/something`)
- **THEN** it returns a tuple of `(crew_id, path_suffix, mount_prefix)` with the correct values

#### Scenario: _extract_crew_proxy_parts returns None for non-proxy path

- **WHEN** `_extract_crew_proxy_parts` is called with a path that does not match the crew proxy pattern (e.g. `/health`)
- **THEN** it returns `None`

#### Scenario: _sanitise_query_string strips dangerous characters

- **WHEN** `_sanitise_query_string` is called with a raw query string containing control characters or null bytes
- **THEN** it returns a string with those characters removed or escaped

#### Scenario: _sanitise_query_string passes through safe query strings

- **WHEN** `_sanitise_query_string` is called with a safe query string (e.g. `foo=bar&baz=1`)
- **THEN** it returns the string unchanged

#### Scenario: _parse_ttl_seconds converts valid integer strings

- **WHEN** `_parse_ttl_seconds` is called with a string representation of a positive integer
- **THEN** it returns the integer value

#### Scenario: _parse_ttl_seconds returns default for invalid input

- **WHEN** `_parse_ttl_seconds` is called with a non-integer string or empty string
- **THEN** it returns the configured default TTL value without raising

#### Scenario: _jwt_exp extracts expiry from a valid JWT

- **WHEN** `_jwt_exp` is called with a well-formed JWT whose payload contains an `exp` claim
- **THEN** it returns the `exp` value as an integer

#### Scenario: _jwt_exp returns None for a malformed token

- **WHEN** `_jwt_exp` is called with a string that is not a valid JWT
- **THEN** it returns `None` without raising

#### Scenario: _cookie_near_expiry returns True for an expiring cookie

- **WHEN** `_cookie_near_expiry` is called with a JWT that expires within the near-expiry threshold
- **THEN** it returns `True`

#### Scenario: _cookie_near_expiry returns False for a fresh cookie

- **WHEN** `_cookie_near_expiry` is called with a JWT whose expiry is well beyond the near-expiry threshold
- **THEN** it returns `False`

#### Scenario: Crew API proxy handler returns 404 on unknown crew

- **WHEN** the crew API proxy handler receives a request for a crew ID not present in the registry
- **THEN** it returns HTTP 404

#### Scenario: Crew API proxy handler constructs correct upstream URL

- **WHEN** the crew API proxy handler proxies a request for a known crew
- **THEN** the upstream URL uses the crew's registered host and port

#### Scenario: UI proxy handler refreshes cookie when gs_session is missing

- **WHEN** the UI proxy handler receives a request with no `gs_session` cookie
- **THEN** a cookie-refresh is attempted before proxying

### Requirement: Health endpoint unit test coverage

The transport health endpoint SHALL be testable by importing the handler
function directly and calling it with a minimal ASGI scope, without starting
a full server.

#### Scenario: _handle_health returns 200 with status ok

- **WHEN** `_handle_health` is called with a minimal GET request scope
- **THEN** the response SHALL be HTTP 200 with a plain-text `ok` body

### Requirement: REST crew payload compatibility has test coverage
The test suite SHALL verify that REST crew records expose canonical `comp`, a same-value `composition` alias, and values matching MCP output.

#### Scenario: REST and MCP crew fields match
- **WHEN** the REST endpoint and MCP `crews()` tool return the same fleet state
- **THEN** the test verifies each crew has equal `comp` and `composition` values in both responses
