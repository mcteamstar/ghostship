# transport-test-coverage — Delta Spec (trn-153-tls-transport-secret-tests)

Updates to the `transport-test-coverage` capability.

## ADDED Requirements

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
