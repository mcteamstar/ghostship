# transport/dashboard-login Specification

## Purpose

The dashboard login page is the sole user-facing HTML page served by the
transport. It SHALL present a polished, on-brand experience that matches
Ghostship's visual identity.

## Requirements

### Requirement: Dashboard login page renders HTML form
`GET /dashboard/login` SHALL serve standalone HTML with a centered 360px `#0f0f0f` card, `#7c3aed` action color and `#6d28d9` hover, and a floating ghost hero. The password field SHALL have an inline vanilla-JS visibility toggle; failed login SHALL shake the error text. Preserve `next` and `csrf_token`, async submit and redirect, and use no external CSS or JavaScript.

#### Scenario: Login page loads
- **WHEN** a browser requests `GET /dashboard/login`
- **THEN** the response is `text/html` with status 200
- **THEN** the page contains a ghost emoji hero element
- **THEN** the submit button background is `#7c3aed`

#### Scenario: Password visibility toggle
- **WHEN** the user clicks the show/hide toggle next to the API key field
- **THEN** the input type toggles between `password` and `text`

#### Scenario: Failed login shows shake animation
- **WHEN** the user submits an incorrect API key
- **THEN** the error paragraph becomes visible with a shake animation class applied
- **THEN** the shake animation plays once and does not repeat until the next failed attempt

#### Scenario: Successful login redirects
- **WHEN** the user submits the correct API key
- **THEN** the browser redirects to the server-sanitised `next` URL
- **THEN** the redirect target comes from the JSON response body, not the raw form field

#### Scenario: Unauthenticated browser is shown login page
- **WHEN** a browser hits a crew dashboard port with no session cookie
- **THEN** it lands on `/dashboard/login?next=<original-url>`
- **THEN** the response is a valid HTML page with a password form

### Requirement: Dashboard login uses a per-page CSRF cookie and form field

Each login page response SHALL issue a fresh random `gs_csrf` cookie with `SameSite=Strict` and `Secure` when TLS is active. The page SHALL echo that cookie in the `csrf_token` form field. The login handler SHALL compare the non-empty cookie and field in constant time and reject missing or mismatched values with HTTP 403 before evaluating the API key.

#### Scenario: Two login page responses issue distinct nonces
- **WHEN** the dashboard login page is rendered twice
- **THEN** the responses issue different `gs_csrf` values, including after an earlier session expires
- **AND** the form echoes the browser's current cookie value

#### Scenario: Missing or forged login CSRF value
- **WHEN** the login form cookie or field is missing or the values differ
- **THEN** the response is HTTP 403 without checking the API key or issuing a session

#### Scenario: Matching login CSRF values
- **WHEN** the cookie and form field match and the API key is valid
- **THEN** login returns HTTP 200 and issues a `gs_session` cookie
