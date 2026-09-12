## Why

Two security-relevant code paths have zero test coverage, flagged by both the security and test-coverage reviewers in the 0.4.0 independent review:

1. `_ssl_context_factory` in `server.py` — direct TLS termination via `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` (legacy path, still active) has no tests at all.
2. `TransportSecretMiddleware` in `auth.py` and `_load_transport_secret` in `server.py` — the internal portal→transport secret gate has no positive or negative coverage.

## What Changes

Add unit tests for both paths. No production code changes.

## Capabilities

### Modified Capabilities

- `transport-test-coverage`: adds required test coverage for TLS context factory and TransportSecretMiddleware.

## Impact

- `tests/unit/test_server.py` or new `tests/unit/test_tls.py` — TLS context factory tests
- `tests/unit/test_auth.py` — TransportSecretMiddleware and `_load_transport_secret` tests
