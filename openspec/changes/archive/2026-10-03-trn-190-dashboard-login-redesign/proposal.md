# TRN-190 — Redesign dashboard login page

## Why

The current `GET /dashboard/login` page is a minimal dark card with a password
input and a green submit button. It works but doesn't match Ghostship's visual
identity. As the only user-facing HTML page the transport serves, it should
look deliberate.

## What Changes

Rewrite the inline HTML in `DashboardGate.handle_login_get`
(`transport/dashboard.py`) to:

- Replace the green button (`#2d6a4f`) with Ghostship purple (`#7c3aed` /
  `#6d28d9` hover)
- Add the ghost emoji (👻) as a large hero element with subtle CSS animation
  (float up/down)
- Add show/hide toggle on the API key password field (eye icon, vanilla JS)
- Surface the `?next=` redirect properly — on successful login the page
  already redirects via the JS fetch handler; no change needed there
- Tighten the card layout: slightly wider (360px), better label spacing
- Show inline error state with a shake animation instead of just
  `display: block` on the error paragraph

## Constraints

- No external dependencies — all CSS/JS inline in the returned HTML string
- No JS framework
- Must keep the existing hidden fields (`next`, `csrf_token`) and form
  structure intact
- Must keep the existing async fetch submit + redirect logic (just restyle)
- Pass existing tests — no functional changes
