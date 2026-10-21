## ADDED Requirements

### Requirement: Gateway error detail reaches the caller
When a request to a crew gateway ends in an HTTP error response after the transport's recovery attempts are exhausted, the error returned to the caller SHALL include the final HTTP status code and the gateway's response body, truncated to at most 500 characters. Any session cookie or token value SHALL be redacted from that text. This SHALL NOT change which responses trigger recovery or how many retries are made.

#### Scenario: Unknown persona is reported, not just "unresponsive"
- **WHEN** a dispatch to a crew whose gateway answers `POST /api/spawn` with HTTP 400 and a body naming an unknown agent exhausts recovery
- **THEN** the error returned to the MCP caller includes `400` and the gateway's reason (for example that agent `ghost` was not found), alongside the existing recovery summary

#### Scenario: Long or credential-bearing bodies are bounded
- **WHEN** the gateway's final error body is longer than 500 characters or contains the crew's session cookie value
- **THEN** the caller receives at most 500 characters of it, with the cookie value replaced by a redaction marker

#### Scenario: Recovery behaviour is unchanged
- **WHEN** a crew gateway returns 400, 401 or 403
- **THEN** cookie refresh, container restart and retry limits behave exactly as under "CSRF/cookie auto-recovery on stale credentials"
