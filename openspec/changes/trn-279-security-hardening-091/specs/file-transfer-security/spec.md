# Spec Delta

## ADDED Requirements

### Requirement: Gateway error response body is redacted before surfacing to callers
Any transport function that surfaces an HTTP error response body from a crew gateway call to an MCP tool caller SHALL redact credential and session material from the body text. At minimum the following patterns SHALL be replaced with a `[redacted]` placeholder before the text reaches any log line or tool response: the crew's session cookie value, `mc_token_<port>=<value>` substrings, any `Authorization: Bearer <value>` substring, and cookie attribute values for `gs_session` and `gs_csrf`. Whitespace SHALL be collapsed and the body SHALL be truncated to a bounded maximum before emission.

#### Scenario: Crew cookie is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains the crew's session cookie value
- **THEN** the error text surfaced to the MCP caller does not contain the raw cookie value; it is replaced with `[redacted]`

#### Scenario: mc_token cookie is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains a `mc_token_<port>=<value>` substring
- **THEN** the error text surfaced to the MCP caller replaces the value with `mc_token=[redacted]`

#### Scenario: Authorization Bearer value is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains an `Authorization: Bearer <token>` substring
- **THEN** the error text surfaced to the MCP caller does not contain the raw token value; the Bearer value is replaced with `[redacted]`

#### Scenario: gs_session cookie value is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains a `gs_session=<value>` cookie substring
- **THEN** the error text surfaced to the MCP caller does not contain the raw session token; it is replaced with `[redacted]`

#### Scenario: gs_csrf cookie value is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains a `gs_csrf=<value>` cookie substring
- **THEN** the error text surfaced to the MCP caller does not contain the raw CSRF token; it is replaced with `[redacted]`

#### Scenario: Body is truncated to a bounded maximum
- **WHEN** a crew gateway returns an HTTP error response with a body longer than the configured maximum
- **THEN** the body is truncated to that maximum length before being surfaced to the caller, regardless of redaction

#### Scenario: Body with no sensitive material passes through (redacted only)
- **WHEN** a crew gateway returns an HTTP error response whose body contains no credential or session material
- **THEN** the error text surfaced to the caller is the (possibly truncated) raw body text with whitespace collapsed, unchanged by the redaction pass
