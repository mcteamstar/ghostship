## Why

The dashboard login path in `transport/server.py` has four security gaps that were deferred during the TRN-92/TRN-103 Portal rollout: the login POST is not throttled against brute-force, the in-memory session store bypasses `security.SessionStore`'s revocation logic, there is no server-side logout route, and the `gs_session` cookie unconditionally sets `Secure` even when the portal runs in plain-HTTP mode. These gaps leave the session gate weaker than the security primitives already shipped in `security.py`.

## What Changes

- **Wire `security.Throttle` into `_handle_dashboard_login_post`**: failed login attempts are tracked per source IP; excessive failures within the window return 429 before credential comparison.
- **Replace `_gs_session_store` dict with `security.SessionStore`**: session issuance and validation go through the existing revocable, bounded store instead of a plain dict with manual expiry checks.
- **Add `POST /dashboard-logout` route**: validates the current `gs_session` cookie, calls `SessionStore.revoke()`, and responds with a `Set-Cookie` header that clears the cookie. Registered as a `public_route` (same pattern as `/dashboard-login`).
- **Conditional `Secure` cookie flag**: `_handle_dashboard_login_post` sets `Secure` on `gs_session` only when `cfg.ga_portal_tls_mode != "off"`, matching the Portal scheme already used for dashboard URLs elsewhere.

## Capabilities

### New Capabilities

- `dashboard-session-auth`: Brute-force throttle on dashboard login, server-side revocable session store, dashboard logout endpoint, and TLS-conditional Secure cookie flag.

### Modified Capabilities

None — all session and login behaviour is new to the dashboard gate introduced in TRN-92; no existing spec describes these server.py internals.

## Impact

- `transport/server.py`: `_handle_dashboard_login_post`, `_gs_session_issue`, `_gs_session_valid`, `_gs_session_store`, new `_handle_dashboard_logout_post`, route table in `BearerAuthMiddleware` construction.
- `transport/security.py`: read-only; `Throttle` and `SessionStore` are already implemented — this change only wires them in.
- `tests/unit/test_server.py`: new test class for dashboard login throttle, logout route, session revocation, and conditional Secure flag.
- `tests/unit/test_trn70_security.py`: existing `Throttle` / `SessionStore` unit tests are unaffected; possibly extended for edge cases surfaced during wiring.
