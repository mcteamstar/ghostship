## ADDED Requirements

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

### Requirement: Health endpoint unit test coverage

The transport health endpoint SHALL be testable by importing the handler
function directly and calling it with a minimal ASGI scope, without starting
a full server.

#### Scenario: _handle_health returns 200 with status ok

- **WHEN** `_handle_health` is called with a minimal GET request scope
- **THEN** the response SHALL be HTTP 200 with a JSON body containing `{"status": "ok"}`
