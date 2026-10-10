## 1. Bind-address warning (install.sh)

- [ ] 1.1 Add `GA_REQUIRE_API_KEY` variable parsing in `scripts/install.sh` after the
  existing variable defaults block; accept `warn`, `error`, `off`; default `warn`
- [ ] 1.2 After the port and API-key variables are resolved, add a check: if
  `GA_API_KEY` is empty and the published port address is not `127.0.0.1`/`::1`,
  emit a WARNING to stderr naming the port; if `GA_REQUIRE_API_KEY=error`, exit
  non-zero; skip the check if `GA_REQUIRE_API_KEY=off`
- [ ] 1.3 Add `GA_REQUIRE_API_KEY` to the compose `environment:` block so it is
  passed to the transport container
- [ ] 1.4 In the transport process startup path (`server.py` or `auth.py` startup
  init), log a `WARNING` when `GA_API_KEY` is absent and `HOST` is not
  `127.0.0.1`/`::1`

## 2. Transport-side WebSocket session validation

- [ ] 2.1 In `transport/server.py` (or the UI proxy handler), locate the WebSocket
  upgrade path for `/crews/{crew_id}/ui/...` and add a `gs_session` cookie check
  via `SessionStore.validate()` before completing the upgrade
- [ ] 2.2 Return HTTP 401 (not a WebSocket upgrade) when the session is absent,
  expired, or revoked; log the rejection at DEBUG level with the crew ID
- [ ] 2.3 Write a test that sends a WebSocket upgrade request to a crew UI path
  without a valid `gs_session` cookie and asserts HTTP 401
- [ ] 2.4 Write a test that sends a WebSocket upgrade with a valid `gs_session`
  cookie and asserts the upgrade is allowed (mocking the downstream proxy)

## 3. Rate-limit source-IP fix (GA_TRUSTED_PROXY)

- [ ] 3.1 Add `GA_TRUSTED_PROXY` to the compose `environment:` block in
  `scripts/install.sh` (defaulting to empty)
- [ ] 3.2 In `transport/auth.py` `RateLimitMiddleware._caller_key()`, read
  `GA_TRUSTED_PROXY` once at middleware construction time; if unset/empty, use
  `scope["client"][0]` exclusively (do not read `X-Forwarded-For`); if set,
  use the last `X-Forwarded-For` hop, falling back to `scope["client"][0]` when
  the header is absent
- [ ] 3.3 Update `test_rate_limiting.py` test(s) that assert first-hop XFF
  behaviour to reflect the new default (ASGI client address); add a test that
  sets `GA_TRUSTED_PROXY=1` and asserts last-hop XFF extraction

## 4. Caddy admin API origins enforcement

- [ ] 4.1 In `scripts/install.sh`, update the `initial-config.json` heredoc to
  add `"origins": ["http://ga-transport"]` inside the `"admin"` object, alongside
  the existing `"listen": "0.0.0.0:2019"` key
- [ ] 4.2 Verify that `_caddy_register_crew()` in `transport/caddy.py` does not
  set an explicit `Origin` header (Caddy's Go HTTP client uses the listen address
  by default — confirm this matches `http://ga-transport` or add the header
  explicitly)
- [ ] 4.3 Add a note to `docs/configuration.md` in the Caddy section that port
  2019 is not host-published and that `origins` enforcement restricts admin-API
  callers to the transport container

## 5. Documentation and configuration

- [ ] 5.1 Add a `GA_REQUIRE_API_KEY` entry to `docs/configuration.md`: three
  values, default, warning behaviour, and when to use `error` or `off`
- [ ] 5.2 Add a `GA_TRUSTED_PROXY` entry to `docs/configuration.md`: what it
  does, default (ASGI client address), and when to set it (installs fronted by an
  external proxy rather than Caddy)
- [ ] 5.3 Add a note in `docs/configuration.md` under TLS / cleartext defaults:
  `GA_PORTAL_TLS_MODE=off` means bearer key, session cookie, and presigned URLs
  travel in plaintext; link to the TLS setup section
- [ ] 5.4 Add commented-out entries for `GA_REQUIRE_API_KEY` and `GA_TRUSTED_PROXY`
  to `config/ghostship.conf.example` with their defaults

## 6. Tests and validation

- [ ] 6.1 Add a test for the `install.sh` warning path: mock a non-loopback bind
  with no API key and assert the warning text appears on stderr (use bats or a
  shell test harness consistent with the project's existing shell tests, if any;
  otherwise document manual verification steps in a comments block)
- [ ] 6.2 Run the full test suite (`pytest` or equivalent) and confirm all
  pre-existing rate-limiting and dashboard-auth tests pass with the changes from
  tasks 2 and 3
- [ ] 6.3 Confirm `openspec validate --change trn-207-network-exposure-defaults
  --store repo` returns clean (no errors)
