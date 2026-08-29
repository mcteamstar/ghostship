## 1. Bug 1 — Auth row token check

- [ ] 1.1 In `_read_auth_from_crew`, extend the row check to verify at least one row has a non-empty `value` field before returning the b64 payload
- [ ] 1.2 Add unit test: `_read_auth_from_crew` returns `None` when `auth_kv` has only a registration row (empty or null `value`)
- [ ] 1.3 Add unit test: `_read_auth_from_crew` returns the b64 payload when `auth_kv` has a row with a non-empty `value`

## 2. Bug 2 — Idle monitor 403 fail-open

- [ ] 2.1 In `_idle_monitor`, extend the cookie-refresh branch from `if r.status_code == 401:` to `if r.status_code in (401, 403):`
- [ ] 2.2 Add unit test: idle monitor attempts cookie refresh and retry on a 403 response (not just 401)
- [ ] 2.3 Add unit test: idle monitor stops the crew after a successful cookie refresh following a 403

## 3. Bug 3 — Cookie header collision in API proxy

- [ ] 3.1 In `_handle_crew_api_proxy`, add `and k.lower() != "cookie"` to the `forward_headers` filter alongside the existing `host` exclusion
- [ ] 3.2 Add unit test: inbound request with a lowercase `cookie` header does not produce duplicate Cookie headers in the forwarded request
- [ ] 3.3 Add unit test: the injected session cookie is present and correct in the forwarded headers when the inbound request had a `cookie` header

## 4. Verification

- [ ] 4.1 Run `bash tests/run.sh --unit` — all tests pass
- [ ] 4.2 Run `bash tests/run.sh --integration` — all tests pass
