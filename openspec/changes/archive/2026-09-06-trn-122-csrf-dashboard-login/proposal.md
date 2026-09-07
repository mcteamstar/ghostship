## Why

`POST /dashboard-login` accepts the `ga_api_key` form field from any origin, making the login endpoint vulnerable to cross-site request forgery: a third-party page could silently submit the form and obtain a `gs_session` cookie if the user has the API key pre-filled or if it is guessable. A CSRF token tied to the server's startup lifetime closes this attack surface at minimal cost.

## What Changes

- A single random 32-byte hex CSRF token (`_dashboard_csrf_token`) is generated at transport startup and held in a module-level constant for the process lifetime.
- `GET /login-ui` (the form page that POSTs to `/dashboard-login`) embeds the token as a hidden `<input name="csrf_token">` field.
- `POST /dashboard-login` reads `csrf_token` from the submitted form and performs a constant-time comparison against `_dashboard_csrf_token`; a mismatch returns HTTP 403 before the API-key check is reached.
- Unit tests in `tests/unit/test_server.py` cover: correct token accepted, missing token rejected (403), wrong token rejected (403), and the token's presence in the rendered form HTML.

## Capabilities

### New Capabilities

- `transport/dashboard-login-csrf`: CSRF protection for the dashboard login form — token generation at startup, embedding in the GET login form, and validation on POST.

### Modified Capabilities

<!-- No existing spec-level requirements change. The transport and crew-login specs
     describe /login (device auth flow), not /dashboard-login. -->

## Impact

- **`transport/server.py`**: adds `_dashboard_csrf_token` module global, modifies `_handle_login_ui` to embed it, modifies `_handle_dashboard_login_post` to validate it.
- **`tests/unit/test_server.py`**: new test class covering CSRF token validation scenarios and form HTML output.
- No external API or cookie contract changes; the hidden field is transparent to JavaScript clients that read the form programmatically (the JS `fetch` path in `_handle_login_ui` already builds `FormData` from the form, so it picks up the hidden field automatically).
- No new dependencies.
