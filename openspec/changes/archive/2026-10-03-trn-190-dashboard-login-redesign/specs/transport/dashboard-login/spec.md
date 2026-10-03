## Purpose

The dashboard login page is the sole user-facing HTML page served by the
transport. It SHALL present a polished, on-brand experience that matches
Ghostship's visual identity.

## MODIFIED Requirements

### Requirement: Dashboard login page renders HTML form
The transport SHALL serve an HTML login page at `GET /dashboard/login` that:
- Displays a centred card on a dark background (`#0f0f0f`)
- Uses Ghostship purple (`#7c3aed`) as the primary action colour, with a
  darker hover state (`#6d28d9`)
- Displays the ghost emoji (👻) as a large, animated hero element above the
  form title, with a continuous float animation (translate Y ±6px, 3s ease-in-out)
- Renders the API key input as a password field with a show/hide toggle
  (eye icon button) implemented in inline vanilla JS
- Displays the card at 360px wide with adequate label and field spacing
- Shows an inline shake animation on the error paragraph when a login attempt
  fails, rather than a plain `display: block` reveal
- Keeps all existing hidden fields (`next`, `csrf_token`), form structure, and
  async fetch submit + redirect logic intact
- Includes no external CSS or JS dependencies — all styles and scripts are
  inline in the returned HTML string

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
