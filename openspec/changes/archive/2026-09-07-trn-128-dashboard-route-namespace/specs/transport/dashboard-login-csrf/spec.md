# transport/dashboard-login-csrf Specification — TRN-128 delta

## Purpose

Updates the CSRF-protected endpoint paths from dash-flat to
slash-namespaced. Functional CSRF behaviour is unchanged.

## MODIFIED Requirements

### Requirement: CSRF endpoints use /dashboard/* paths

The CSRF token SHALL be embedded in `GET /dashboard/login-ui` (not `GET /login-ui`)
and validated on `POST /dashboard/login` (not `POST /dashboard-login`).
All existing CSRF functional requirements apply at the new paths.

#### Scenario: Token present at new login-ui path

- **WHEN** a client requests `GET /dashboard/login-ui`
- **THEN** the response body contains `<input type="hidden" name="csrf_token"` with the current `_dashboard_csrf_token` value

#### Scenario: CSRF validation at new login path

- **WHEN** `POST /dashboard/login` is called with a missing or wrong `csrf_token`
- **THEN** the handler returns HTTP 403
