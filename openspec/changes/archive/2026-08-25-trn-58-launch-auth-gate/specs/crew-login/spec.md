## NEW Scenarios

### Scenario: Login flow initiated from within launch (no existing pending flow)
- **WHEN** `launch` is called without valid auth, no login flow is currently pending, and `_initiate_login()` is called internally
- **THEN** a `ga-login-<token>` container is started, `_login_pending` is set to a non-None sentinel before the lock is released (same TOCTOU guard as a direct `POST /login` call), and `login_url` and `code` are extracted and returned to the caller via the `launch` error response — the background drain thread continues running to completion

### Scenario: Login flow initiated from within launch (flow already pending)
- **WHEN** `launch` is called without valid auth and a login flow is already in progress (the `_login_pending` sentinel is set)
- **THEN** `launch` does NOT start a second container; the response includes `error: "not_authenticated"` and `login_pending: true` so the caller knows to poll `GET /login`
