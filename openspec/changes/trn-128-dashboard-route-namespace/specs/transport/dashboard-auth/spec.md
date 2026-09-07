# transport/dashboard-auth Specification — TRN-128 delta

## Purpose

Updates the route paths for all dashboard auth endpoints from dash-flat to
slash-namespaced. Functional behaviour is unchanged; only externally visible
URL paths change.

## MODIFIED Requirements

### Requirement: Dashboard auth endpoints use /dashboard/* paths

The transport SHALL expose the following routes under the `/dashboard/` prefix:

- `GET /dashboard/auth` — Caddy `forward_auth` target (replaces `GET /dashboard-auth`)
- `POST /dashboard/login` — API-key validation and session-cookie issuance (replaces `POST /dashboard-login`)
- `POST /dashboard/logout` — session revocation and cookie clearing (replaces `POST /dashboard-logout`)
- `GET /dashboard/login-ui` — HTML login form (replaces `GET /login-ui`)

The old paths (`/dashboard-auth`, `/dashboard-login`, `/dashboard-logout`, `/login-ui`) SHALL NOT be served.

#### Scenario: forward_auth uses new path

- **WHEN** Caddy's `forward_auth` handler fires for a crew dashboard request
- **THEN** it calls `GET /dashboard/auth?port=<port>` on the transport (not `/dashboard-auth`)

#### Scenario: Login form POST target is /dashboard/login

- **WHEN** a browser requests `GET /dashboard/login-ui`
- **THEN** the response HTML form's `action` attribute is `/dashboard/login`
- **THEN** the JS `fetch` call also targets `/dashboard/login`

#### Scenario: 401 redirects to /dashboard/login-ui

- **WHEN** a browser hits a crew dashboard port with no valid session
- **THEN** Caddy redirects the browser to `/dashboard/login-ui?next=<original-url>`
