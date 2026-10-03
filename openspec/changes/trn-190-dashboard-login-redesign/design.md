## Context

See proposal.md — Why. The login HTML lives entirely in
`DashboardGate.handle_login_get` (`transport/dashboard.py`) as an inline
f-string. No template engine, no external assets — the entire page is one
Python string returned as a `text/html` response.

The existing form structure, CSRF handling, and async fetch submit logic are
correct and must be preserved. This change is purely cosmetic.

## Goals / Non-Goals

**Goals:**
- Replace green button with Ghostship purple
- Add ghost emoji hero with float animation
- Add password show/hide toggle (vanilla JS)
- Shake animation on failed login
- Tighten card to 360px with better spacing

**Non-Goals:**
- Any change to POST /dashboard/login logic
- Any change to CSRF, throttle, session, or redirect handling
- External dependencies, fonts, or CDN assets
- Changing the existing test surface (no functional change)

## Decisions

**D1 — All CSS/JS stays inline in the f-string**
The transport serves no static files. Keeping everything inline in
`handle_login_get` is the only viable pattern and is consistent with the
existing page. No change to the server routing or static file handling needed.

**D2 — Show/hide toggle uses a `<button type="button">` with an SVG eye icon**
A `<button type="button">` prevents form submission on click. The toggle
switches `input.type` between `password` and `text` via inline JS. The icon
is an inline SVG (no external image request). Alternative considered: a
checkbox — rejected because it requires label wiring and is less conventional
UX for password fields.

**D3 — Shake animation via CSS `@keyframes` + a toggled class**
On failed login, JS adds a `shake` class to the error paragraph; the class is
removed after the animation duration (`animationend` event) so the animation
re-triggers on subsequent failures. Alternative considered: CSS animation on
the input field — rejected because the error paragraph is the natural locus of
failure feedback.

**D4 — Float animation on the ghost emoji is pure CSS, `animation: float 3s ease-in-out infinite`**
No JS needed. The emoji sits in a `<div class="hero">` above the card title.
The float is subtle (±6px translateY) — decorative, not distracting.

## Risks / Trade-offs

- **Inline HTML string grows** — The f-string in `handle_login_get` will be
  longer. Not a maintenance concern at this scale (single page, rarely edited).
  → No mitigation needed.
- **Emoji rendering varies by OS** — 👻 renders differently on macOS vs Linux.
  The difference is cosmetic and acceptable for a developer-facing admin page.
  → No mitigation needed.
