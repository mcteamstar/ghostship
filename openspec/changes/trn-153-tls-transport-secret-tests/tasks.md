## 1. TLS context factory tests

- [ ] 1.1 Create `tests/unit/test_tls.py` (or add to `test_server.py`)
- [ ] 1.2 Add test: `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` not set → no `ssl_context_factory` in uvicorn kwargs
- [ ] 1.3 Add test: both set to valid temp files → `ssl_context_factory` registered, returns context with `PROTOCOL_TLS_SERVER` and min version TLS 1.2
- [ ] 1.4 Add test: cert file path does not exist → raises at startup

## 2. TransportSecretMiddleware tests

- [ ] 2.1 Add tests to `tests/unit/test_auth.py`
- [ ] 2.2 Add test: secret not configured (`GA_TRANSPORT_SECRET` empty) → request passes through (no 401)
- [ ] 2.3 Add test: secret configured, correct `X-Portal-Token` → passes through
- [ ] 2.4 Add test: secret configured, wrong `X-Portal-Token` → 401
- [ ] 2.5 Add test: secret configured, no `X-Portal-Token` header → 401
- [ ] 2.6 Add test: token comparison uses `hmac.compare_digest` (not `==`)

## 3. _load_transport_secret tests

- [ ] 3.1 Add test: secret file present and readable → returns content stripped
- [ ] 3.2 Add test: secret file absent, env var fallback absent → returns empty string (or raises — verify current behaviour first)

## 4. Verification

- [ ] 4.1 Run full unit suite — all pass
