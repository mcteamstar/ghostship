# Tasks

## 1. Transport auth refresh operation

- [x] 1.1 Implement a shared per-crew refresh operation that resolves the recorded backend/profile, serializes against credential replacement/logout, injects current flow credentials into running crews, and returns the specified state outcomes; compare static values with `hmac.compare_digest` and keep credential values out of logs, exception text and tracebacks; verify tests cover success, stopped flow, static match/mismatch, missing credential, injection failure, a comparison error, and secret redaction.
- [x] 1.2 Expose the operation through bearer-protected `POST /crews/{crew_id}/auth/refresh` and transport-secret-protected `POST /internal/crews/{crew_id}/auth/refresh`, including browser-Origin rejection and OpenAPI registration; return HTTP 200 with `status` for every defined outcome and 404 only for an unknown crew; verify auth tests cover bearer, internal-token, Origin, and unknown-crew cases, assert status codes per outcome, and OpenAPI lists both routes.

## 2. Portal and Radar operator action

- [x] 2.1 Add Radar's `POST /api/crews/{crew_id}/auth/refresh` proxy to the internal transport route, rejecting requests whose `Origin` is missing or does not match the request host with 403 before calling Transport; verify Radar tests assert token forwarding, outcome passthrough, safe 502 behavior, and Origin rejection (missing, cross-origin, same-origin accepted).
- [x] 2.2 Add a per-crew auth refresh action in the Radar detail panel and display refreshed, pending-on-wake, current, recreate-required, missing, and failed outcomes; call the endpoint with `redirect: "manual"` (or detect a redirected/non-JSON response) and show a sign-in-again message on session expiry; verify the UI disables duplicate submissions, handles the expired-session redirect, and renders actionable text without credential data.
- [x] 2.3 Preserve Portal session gating for the mutating Radar endpoint; verify generated Caddy config routes the POST through `forward_auth` when API-key auth is enabled and the request reaches Radar only for an authenticated session.

## 3. Auth guidance

- [x] 3.1 Update `docs/auth.md` with the operator API, refresh outcomes, existing flow behavior, static credential recovery, and approximate Codex ChatGPT (~10 days) and Kiro Identity Center (~90 days) lifetimes; verify the examples match the implemented routes and describe lifetime values as estimates.
- [ ] 3.2 Update `docs/radar.md` with the Portal action, operator-facing outcome guidance, the same-origin requirement, and a note that Tailscale-gated installs expose the action without a portal session; verify the documented UI behavior matches the Radar implementation.
