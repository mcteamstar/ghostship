## 1. Scaffold test file and shared helpers

- [x] 1.1 Create `tests/unit/test_auth.py` with the module docstring, imports (`unittest`, `hmac`, `os`, `asyncio`, `unittest.mock`), and the `_make_scope(method, path, headers=None)` helper that returns a minimal ASGI HTTP scope dict.
- [x] 1.2 Add the `_collect_send()` async helper and `_run(coro)` sync wrapper (calls `asyncio.get_event_loop().run_until_complete`) that test methods use to invoke middleware `__call__` synchronously.
- [x] 1.3 Confirm `python -m pytest tests/unit/test_auth.py --collect-only` succeeds with an empty file (no import errors).

## 2. Tests for _parse_bearer_token

- [x] 2.1 Add `class TestParseBearerToken(unittest.TestCase)` and import `_parse_bearer_token` from `transport.auth`.
- [x] 2.2 Write `test_well_formed_token` — `_parse_bearer_token("Bearer abc123")` returns `"abc123"`.
- [x] 2.3 Write `test_case_insensitive_scheme` — `_parse_bearer_token("BEARER mytoken")` returns `"mytoken"`.
- [x] 2.4 Write `test_missing_scheme_returns_none` — bare token string returns `None`.
- [x] 2.5 Write `test_wrong_scheme_returns_none` — `"Basic abc123"` returns `None`.
- [x] 2.6 Write `test_token_with_embedded_space_returns_none` — `"Bearer a b"` returns `None`.
- [x] 2.7 Write `test_empty_string_returns_none`.
- [x] 2.8 Write `test_too_short_returns_none` — string shorter than 8 characters returns `None`.

## 3. Tests for _parse_rate_limit_var

- [x] 3.1 Add `class TestParseRateLimitVar(unittest.TestCase)` and import `_parse_rate_limit_var`.
- [x] 3.2 Write `test_valid_env_var_parsed` — env var `"10:60"` returns `(10, 60)`.
- [x] 3.3 Write `test_env_var_absent_returns_defaults` — missing env var returns supplied `(count, window)` defaults.
- [x] 3.4 Write `test_non_integer_returns_defaults_and_warns` — assert defaults returned and WARNING logged.
- [x] 3.5 Write `test_zero_count_returns_defaults_and_warns`.
- [x] 3.6 Write `test_negative_window_returns_defaults_and_warns`.

## 4. Tests for _build_rate_limiters

- [x] 4.1 Add `class TestBuildRateLimiters(unittest.TestCase)` and import `_build_rate_limiters`.
- [x] 4.2 Write `test_master_switch_false_returns_none` — `GA_RATE_LIMIT_ENABLED=false` → `None`.
- [x] 4.3 Write `test_master_switch_true_returns_populated_dict` — absent or `"true"` → dict keyed by `"login_post"`, `"login_get"`, `"files"`, `"crew_api"`, `"mcp"`, `"dashboard_auth"`.

## 5. Tests for _request_source

- [x] 5.1 Add `class TestRequestSource(unittest.TestCase)` and import `_request_source`.
- [x] 5.2 Write `test_xff_first_hop_from_scope` — scope with `x-forwarded-for: "1.2.3.4, 5.6.7.8"` returns `"1.2.3.4"`.
- [x] 5.3 Write `test_asgi_client_ip_when_no_xff` — scope with `client=("10.0.0.1", 1234)` and no XFF header returns `"10.0.0.1"`.
- [x] 5.4 Write `test_none_when_source_unavailable` — empty scope (no headers, no client) returns `None`.

## 6. Tests for TransportSecretMiddleware

- [x] 6.1 Add `class TestTransportSecretMiddleware(unittest.TestCase)`, import the class. Define a minimal downstream `app` that records calls.
- [x] 6.2 Write `test_correct_token_passes_through` — middleware configured with `"s3cr3t"` passes when `X-Transport-Token: s3cr3t` is present; downstream app called.
- [x] 6.3 Write `test_wrong_token_returns_401` — wrong token → 401; downstream NOT called.
- [x] 6.4 Write `test_missing_token_returns_401` — no `X-Transport-Token` header → 401.
- [x] 6.5 Write `test_empty_secret_passthrough` — empty `transport_secret=""` → all requests pass regardless of header value.
- [x] 6.6 Write `test_non_http_scope_passthrough` — WebSocket scope with wrong token still passes to downstream (non-HTTP bypass).
- [x] 6.7 Write `test_constant_time_compare_used` — use `unittest.mock.patch("transport.auth.hmac.compare_digest")` and assert it was called when a token is present.

## 7. Tests for RateLimitMiddleware

- [x] 7.1 Add `class TestRateLimitMiddleware(unittest.TestCase)`. Create a factory `_make_middleware(limiters, api_key="")` that wraps a recording downstream app.
- [x] 7.2 Write `test_health_exempt` — GET `/health` passes without rate check (no limiter recorded).
- [x] 7.3 Write `test_version_exempt` — GET `/version` passes without rate check.
- [x] 7.4 Write `test_first_request_within_limit_passes` — first request to `/login` (POST) with a fresh limiter (`max_requests=5, window_secs=60`) passes.
- [x] 7.5 Write `test_over_limit_returns_429` — after exhausting the limit, next request returns 429 with `Retry-After` header; downstream NOT called.
- [x] 7.6 Write `test_caller_key_ip_only_when_no_bearer` — construct two different-IP requests; assert they track separately by asserting one passes while the other is at limit.
- [x] 7.7 Write `test_caller_key_hashes_bearer_when_present` — assert that `SHA-256(token)[:8]:<ip>` is the key format by using a limiter with `max_requests=1` and sending two requests from the same IP but different tokens; both should be tracked independently.
- [x] 7.8 Write `test_unmatched_path_passthrough` — GET `/some/other/path` passes without any rate-limit record.
- [x] 7.9 Write `test_login_post_matched` — `POST /login` → `login_post` limiter consumed.
- [x] 7.10 Write `test_login_get_matched` — `GET /login` → `login_get` limiter consumed.
- [x] 7.11 Write `test_files_path_matched` — `GET /files/abc` → `files` limiter consumed.
- [x] 7.12 Write `test_crew_api_path_matched` — `GET /crews/xyz/api/foo` → `crew_api` limiter consumed.
- [x] 7.13 Write `test_mcp_path_matched` — `GET /mcp/list` → `mcp` limiter consumed.

## 8. Tests for BearerAuthMiddleware — pass-through and rejection paths

- [x] 8.1 Add `class TestBearerAuthMiddleware(unittest.TestCase)`. Create a factory `_make_mw(api_key, routes=None, public_routes=None, file_app=None)` wrapping a recording downstream app.
- [x] 8.2 Write `test_correct_bearer_passes` — correct `Authorization: Bearer <key>` → downstream called.
- [x] 8.3 Write `test_wrong_bearer_returns_401` — wrong key → 401 with `WWW-Authenticate: Bearer`.
- [x] 8.4 Write `test_missing_auth_header_returns_401`.
- [x] 8.5 Write `test_duplicate_auth_headers_returns_401` — two `authorization` headers → 401.
- [x] 8.6 Write `test_malformed_auth_header_returns_401` — `Authorization: Token abc` → 401.
- [x] 8.7 Write `test_health_bypasses_bearer` — `/health` passes with no auth header when api_key is set.
- [x] 8.8 Write `test_empty_api_key_passthrough` — `api_key=""` → downstream called with no auth header present.
- [x] 8.9 Write `test_constant_time_compare_used` — patch `transport.auth.hmac.compare_digest`; assert called during token validation.
- [x] 8.10 Write `test_audit_event_emitted_on_rejection` — patch `transport.auth._security.audit_auth_event`; assert called with `outcome="denied"` when wrong token is supplied.

## 9. Tests for BearerAuthMiddleware — route dispatch

- [x] 9.1 Write `test_public_route_dispatched_without_auth` — register a handler in `public_routes` for `("GET", "/pub")`; no `Authorization` header; assert handler called, downstream NOT called.
- [x] 9.2 Write `test_files_forwarded_to_file_app_bypassing_bearer` — set `file_app` to a recording app; request path `/files/x`; assert file_app called and downstream NOT called even without auth header.
- [x] 9.3 Write `test_registered_route_dispatched_after_auth` — register a handler in `routes` for `("GET", "/tool")`; send correct bearer; assert handler called, downstream NOT called.
- [x] 9.4 Write `test_ws_upgrade_dispatched_without_bearer` — construct an ASGI WebSocket scope for `/crews/abc/ui/x`; register WS handler under `public_routes[("WS", "/crews/*/ui")]`; assert handler called.

## 10. Tests for SecurityHeadersMiddleware

- [x] 10.1 Add `class TestSecurityHeadersMiddleware(unittest.TestCase)`. Create a factory wrapping a trivial 200 OK downstream app.
- [x] 10.2 Write `test_security_headers_added` — send HTTP request; assert `x-content-type-options` present in response headers.
- [x] 10.3 Write `test_hsts_on_https_response` — set `X-Forwarded-Proto: https`; assert `strict-transport-security` with non-zero `max-age` present.
- [x] 10.4 Write `test_hsts_absent_on_http_response` — plain HTTP request; assert no `strict-transport-security` header.
- [x] 10.5 Write `test_xfp_detection` — ASGI scheme `http` but `X-Forwarded-Proto: https` → `_is_https()` returns `True`.
- [x] 10.6 Write `test_enforce_redirect_sends_301` — `enforce_redirect=True`, plain HTTP, non-health path → 301 with `Location: https://...`.
- [x] 10.7 Write `test_health_not_redirected` — `enforce_redirect=True`, plain HTTP, path `/health` → downstream called (no redirect).
- [x] 10.8 Write `test_control_chars_stripped_from_redirect_target` — path contains `\x0d\x0a`; assert `Location` header has no control characters.
- [x] 10.9 Write `test_headers_disabled_when_flag_false` — `enable_headers=False`; assert no security headers injected.
- [x] 10.10 Write `test_non_http_scope_passthrough` — WebSocket scope; assert downstream called and no header injection attempted.

## 11. Validation and run

- [x] 11.1 Run `pytest tests/unit/test_auth.py -v` and confirm all tests pass.
- [x] 11.2 Run `openspec validate trn-248-test-auth --store repo` and confirm no errors.
