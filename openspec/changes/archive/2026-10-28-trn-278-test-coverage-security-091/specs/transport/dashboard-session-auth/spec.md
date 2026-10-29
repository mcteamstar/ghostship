## MODIFIED Requirements

### Requirement: handle_auth and handle_logout_post have direct unit tests

`tests/unit/test_dashboard.py` SHALL include direct tests for `DashboardGate.handle_auth`
and `DashboardGate.handle_logout_post` covering the following cases:

- `handle_auth` with a valid unexpired `gs_session` cookie returns HTTP 200
- `handle_auth` with an expired `gs_session` cookie returns HTTP 401
- `handle_auth` with a revoked `gs_session` cookie (after logout) returns HTTP 401
- `handle_logout_post` revokes the session so subsequent `handle_auth` calls return 401

#### Scenario: Valid session passes auth check
- **WHEN** `handle_auth` is called with a request carrying a valid `gs_session` cookie
- **THEN** the response status is 200

#### Scenario: Expired session fails auth check
- **WHEN** `handle_auth` is called with a request carrying an expired `gs_session` cookie
- **THEN** the response status is 401

#### Scenario: Revoked session fails auth check after logout
- **WHEN** `handle_logout_post` is called for a session and then `handle_auth` is called with that session's cookie
- **THEN** `handle_auth` returns 401
