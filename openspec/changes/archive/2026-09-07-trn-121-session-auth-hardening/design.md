## Context

See proposal.md — Why.

`transport/server.py` currently manages dashboard sessions with a bare `dict[str, float]` (`_gs_session_store`) and a pair of helper functions (`_gs_session_issue` / `_gs_session_valid`). The `security` module already ships `Throttle` (sliding-window failed-attempt throttle) and `SessionStore` (bounded, revocable token store) but neither is wired into the login path. The `ga_portal_tls_mode` config field exists and is already used to determine the Caddy scheme for dashboard URLs; it is not yet consulted when building the `Set-Cookie` header.

## Goals / Non-Goals

**Goals:**
- Wire `security.Throttle` into `_handle_dashboard_login_post` so repeated failures from the same source IP are blocked at 429 before the credential comparison.
- Replace `_gs_session_store` dict with a `security.SessionStore` instance; remove `_gs_session_store_lock`, `_gs_session_issue`, and `_gs_session_valid` in favour of the store's `issue()` and `validate()` methods.
- Add `POST /dashboard-logout`: validate the cookie, call `store.revoke()`, emit a clearing `Set-Cookie`.
- Make the `Secure` flag conditional on `cfg.ga_portal_tls_mode != "off"`.

**Non-Goals:**
- Persistent (cross-restart) session storage — in-memory is acceptable per the existing design decision.
- Per-user session tracking or multi-user login — the dashboard gate is single-bearer-key only.
- Changes to `security.Throttle` or `security.SessionStore` themselves.
- Changes to the Caddy-side forward-auth logic.

## Decisions

### D1 — Module-level `Throttle` and `SessionStore` instances

A single `_dashboard_throttle = _security.Throttle(max_failures=5, window_secs=900)` and `_gs_sessions = _security.SessionStore(lifetime_secs=cfg.ga_portal_session_ttl_secs)` are created at module level, matching the existing pattern for `_gs_session_store`. Both carry their own internal lock so no external locking is needed.

**Alternative considered**: Create them inside the handler on first call, guarded by a module-level lock. Rejected — adds unnecessary complexity; module-level initialisation is correct and simpler.

### D2 — Throttle key is the request source IP

`_request_source(request)` is already imported from `transport.auth` and used by `audit_auth_event` calls. It returns a normalized source string (IP or forwarded header). Using it as the throttle key is consistent and avoids duplicating IP-extraction logic.

**Alternative considered**: Key on `(source, account)`. Rejected — there is only one account (the single GA_API_KEY), so the account dimension adds no discrimination.

### D3 — 429 before constant-time compare when throttled

When `_dashboard_throttle.is_locked(...)` returns `True`, the handler returns 429 immediately without calling `hmac.compare_digest`. This avoids a timing oracle on the reject path and is safe: the throttle window already precludes statistical analysis of response timing.

### D4 — `POST /dashboard-logout` registered as a `public_route`

`/dashboard-login` and `/login-ui` are already in `public_routes` in the `BearerAuthMiddleware` constructor call. `/dashboard-logout` follows the same pattern: it authenticates via the `gs_session` cookie it reads, not via the Bearer API key. Placing it in `public_routes` keeps it on the same code path as `/dashboard-login`.

### D5 — Cookie-clearing `Set-Cookie` header uses `Max-Age=0`

`Max-Age=0` is the most portable attribute for an immediate-delete across browsers and frameworks. `Expires=<epoch>` is equivalent but less reliable in strict RFC 6265 parsers. Both attributes are emitted for belt-and-suspenders compatibility. The cookie name, `Path=/`, `HttpOnly`, and `SameSite=Lax` match the issuance attributes so the browser's cookie store removes the right entry.

### D6 — `_gs_session_store` helper functions removed

`_gs_session_issue` and `_gs_session_valid` become thin wrappers around the new store; removing them and calling `_gs_sessions.issue()` / `_gs_sessions.validate()` directly eliminates dead code. `_gs_session_store_lock` is also removed — `SessionStore` carries its own lock.

## Risks / Trade-offs

- **In-memory throttle resets on restart** → acceptable; the same constraint applies to `_gs_sessions`. A restarting transport that is under active brute-force attack is not meaningfully harmed — the attacker only regains a 15-minute window.
- **Single `SessionStore` instance limits horizontal scaling** → accepted per the existing single-process deployment model. Adding Redis-backed storage is a later follow-on.
- **Removing `_gs_session_store_lock` is a behaviour change** → no external caller references `_gs_session_store` or the lock directly; both are module-private. The `SessionStore` class uses its own internal lock with equivalent semantics.

## Migration Plan

1. Add module-level `_dashboard_throttle` and `_gs_sessions` instances.
2. Rewrite `_handle_dashboard_login_post` to check throttle → compare credential → reset/record → issue via store → build conditional `Set-Cookie`.
3. Rewrite `_handle_dashboard_auth` to call `_gs_sessions.validate()` instead of `_gs_session_valid()`.
4. Remove `_gs_session_store`, `_gs_session_store_lock`, `_gs_session_issue`, `_gs_session_valid`.
5. Add `_handle_dashboard_logout_post` and wire into `public_routes`.
6. Add / update tests in `test_server.py` covering each spec scenario.

No config changes, no migration of existing live sessions (in-memory, acceptable to invalidate on deploy).
