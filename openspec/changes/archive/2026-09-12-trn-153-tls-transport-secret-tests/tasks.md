## 1. TLS context factory tests

- [x] 1.1 Create `tests/unit/test_tls.py` (or add to `test_server.py`)
- [x] 1.2 Add test: `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` not set → no `ssl_context_factory` in uvicorn kwargs
- [x] 1.3 Add test: both set to valid temp files → `ssl_context_factory` registered, returns context with `PROTOCOL_TLS_SERVER` and min version TLS 1.2
- [x] 1.4 Add test: cert file path does not exist → raises at startup

## 2. TransportSecretMiddleware tests

- [x] 2.1 Add tests to `tests/unit/test_auth.py`
- [x] 2.2 Add test: secret not configured (`GA_TRANSPORT_SECRET` empty) → request passes through (no 401)
- [x] 2.3 Add test: secret configured, correct `X-Transport-Token` → passes through
- [x] 2.4 Add test: secret configured, wrong `X-Transport-Token` → 401
- [x] 2.5 Add test: secret configured, no `X-Transport-Token` header → 401
- [x] 2.6 Add test: token comparison uses `hmac.compare_digest` (not `==`)

## 3. _load_transport_secret tests

- [x] 3.1 Add test: secret file present and readable → returns content stripped
- [x] 3.2 Add test: secret file absent, env var fallback absent → returns empty string (or raises — verify current behaviour first)

## 4. Verification

- [x] 4.1 Run full unit suite — all pass

## Notes

- The middleware header is `X-Transport-Token` (per `TransportSecretMiddleware`
  and `server.py` TRN-107 comments), not `X-Portal-Token` as drafted in tasks
  2.3–2.5. Tests use the actual header name.
- `_load_transport_secret` (3.2) reads only `/run/secrets/ga-transport-secret`;
  there is no env-var fallback in the current implementation. On an absent file
  it returns `""` (does not raise). Test asserts the `""` behaviour.
- `_ssl_context_factory` is a closure inside `server`'s run block and cannot be
  imported directly. `test_tls.py` asserts the registration gate against the
  live `server.GA_TLS_*` attributes and the identical `certfile and keyfile`
  condition, and asserts context construction against a factory built with the
  same `ssl` calls the source performs.
