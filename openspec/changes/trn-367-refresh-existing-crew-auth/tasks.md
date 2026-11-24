# Tasks

## 1. Transport auth refresh operation

- [ ] 1.1 Implement a shared per-crew refresh operation that resolves the recorded backend/profile, serializes against credential replacement/logout, injects current flow credentials into running crews, and returns the specified state outcomes; verify tests cover success, stopped flow, static match/mismatch, missing credential, injection failure, and secret redaction.
- [ ] 1.2 Expose the operation through bearer-protected `POST /crews/{crew_id}/auth/refresh` and transport-secret-protected `POST /internal/crews/{crew_id}/auth/refresh`, including browser-Origin rejection and OpenAPI registration; verify auth tests cover bearer, internal-token, Origin, and unknown-crew cases and OpenAPI lists both routes.

## 2. Portal and Radar operator action

- [ ] 2.1 Add Radar's `POST /api/crews/{crew_id}/auth/refresh` proxy to the internal transport route; verify Radar tests assert token forwarding, outcome passthrough, and safe 502 behavior.
- [ ] 2.2 Add a per-crew auth refresh action in the Radar detail panel and display refreshed, pending-on-wake, current, recreate-required, missing, and failed outcomes; verify the UI disables duplicate submissions and renders actionable text without credential data.
- [ ] 2.3 Preserve Portal session gating for the mutating Radar endpoint; verify generated Caddy config routes the POST through `forward_auth` when API-key auth is enabled and the request reaches Radar only for an authenticated session.

## 3. Auth guidance

- [ ] 3.1 Update `docs/auth.md` with the operator API, refresh outcomes, existing flow behavior, static credential recovery, and approximate Codex ChatGPT (~10 days) and Kiro Identity Center (~90 days) lifetimes; verify the examples match the implemented routes and describe lifetime values as estimates.
- [ ] 3.2 Update `docs/radar.md` with the Portal action and operator-facing outcome guidance; verify the documented UI behavior matches the Radar implementation.
