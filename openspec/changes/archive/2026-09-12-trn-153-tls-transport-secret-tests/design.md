## Context

`_ssl_context_factory` lives in `server.py`'s startup block, gated on `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE`. It's a legacy direct-TLS path predating the Caddy portal. It's still present and active but completely untested.

`TransportSecretMiddleware` in `auth.py` is the innermost security gate — every request to the transport must carry the correct `X-Transport-Token` injected by Caddy. `_load_transport_secret` in `server.py` reads it from `/run/secrets/ga-transport-secret`. Both have zero test coverage.

## Goals / Non-Goals

**Goals:**
- Unit tests for `_ssl_context_factory`: disabled, enabled, file-missing paths
- Unit tests for `TransportSecretMiddleware`: pass-through when unconfigured, correct/wrong/missing token
- Unit test for `_load_transport_secret`: file present, file absent

**Non-Goals:**
- Changing any production code
- Integration tests requiring a real TLS handshake

## Decisions

**D1 — Test _ssl_context_factory with tmp_path cert files**

Create minimal self-signed cert/key files in a temp directory using Python's `ssl` module or `cryptography` (already a transitive dep). Test the factory function directly, not the full uvicorn startup.

**D2 — Test TransportSecretMiddleware as an ASGI app**

`TransportSecretMiddleware` is an ASGI middleware. Use `httpx2.AsyncClient(transport=httpx2.ASGITransport(...))` to send test requests through it, matching the pattern already established in `test_auth.py` for `BearerAuthMiddleware`.

**D3 — Confirm constant-time compare via inspection or mock**

Assert that `hmac.compare_digest` is called (not `==`) by inspecting the source or patching `hmac.compare_digest` to verify it's invoked.

## Risks / Trade-offs

- TLS tests require generating a minimal cert/key pair — small test setup cost.
- `_ssl_context_factory` is only reachable when `GA_TLS_CERTFILE` is set, so tests must set the module-level globals directly.
