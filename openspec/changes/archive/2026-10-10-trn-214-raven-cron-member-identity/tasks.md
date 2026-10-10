# Tasks: TRN-214 Stage 2 — Internal Cookie Mint

Stage 1 (dispatch+steer loop) is implemented and deployed.
Stage 2 first attempt (external cookie injection, commit `434fcf7`) failed integration
testing — external cookie is IP-bound to transport host, `403 IP mismatch` from inside
container. Revised approach: mint internal cookie from inside the container.

## Already done (from first attempt, `434fcf7`)

- [x] `_write_dashboard_cookie` helper in lifecycle.py (unchanged, still used)
- [x] `_write_dashboard_cookie` call sites in `_finish_crew_setup`, `_ensure_crew_running`,
  `_dispatch_captain_checkin`, `_steer_captain_checkin`
- [x] `_write_dashboard_cookie` in both server.py import blocks
- [x] 6 unit tests for write helper passing; 1216 total passing

## 1. Add `_mint_internal_cookie` helper

- [x] 1.1 In `transport/lifecycle.py`, add `_mint_internal_cookie(podman, container)`:
  - `podman exec` → `kirocrew token --ttl 24h` → parse `?token=<jwt>` from output
  - `podman exec` → `curl -si "http://localhost:{CREW_GATEWAY_PORT}/?token={token}"`
  - Parse `mc_token_{CREW_GATEWAY_PORT}=<value>` from `Set-Cookie` in curl output
  - Return value string or `None` on any failure (log WARNING on failure)

## 2. Call `_mint_internal_cookie` at setup and store in registry

- [x] 2.1 In `_finish_crew_setup`: after `cookie = _mint_cookie(...)`, call
  `internal_cookie = _mint_internal_cookie(podman, container)` and pass to
  `_write_dashboard_cookie`. Store `internal_cookie` in the registry entry
  under key `"internal_cookie"` (same as `"cookie"` is stored).
- [x] 2.2 In `_ensure_crew_running` restart path: `_refresh_cookie` is already called
  here — no separate `_mint_internal_cookie` call needed (covered by task 3 below).

## 3. Extend `_refresh_cookie` to refresh both cookies

- [x] 3.1 In `_refresh_cookie`: after minting and storing `new_cookie`, also call
  `new_internal = _mint_internal_cookie(podman, crew["container"])`.
- [x] 3.2 If `new_internal`: store in registry as `internal_cookie`, call
  `_write_dashboard_cookie(podman, crew["container"], new_internal)`.
- [x] 3.3 If `new_internal` is None: log WARNING, leave existing `.dashboard_cookie`
  in place (non-fatal). `_refresh_cookie` still returns True if external cookie succeeded.

## 4. Update `_dispatch_captain_checkin` and `_steer_captain_checkin`

- [x] 4.1 In both: read `internal_cookie` from registry (not `crew["cookie"]`). If
  present, call `_write_dashboard_cookie(podman, container, internal_cookie)` as
  belt-and-suspenders (ensure file is current). If absent, skip — `_refresh_cookie`
  will populate it next cycle. Do NOT call `_mint_internal_cookie` here (avoid
  fresh mint on every Captain tick).

## 5. Update `_RAVEN_GATEWAY_ORIENTATION`

- [x] 5.1 In `transport/captain.py`, rewrite the REST call auth instructions to use
  cookie-only for ALL four spawn endpoints. Cookie auth (`Cookie: mc_token_5476=...`)
  is admitted unconditionally on all spawn endpoints — `X-Internal-Secret` must NOT
  be sent alongside the cookie (it overrides to `internal_auth` and ignores the cookie).
  Example spawn call:
  ```bash
  COOKIE=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)
  curl -s -X POST http://localhost:5476/api/spawn \
    -H "Cookie: mc_token_5476=$COOKIE" \
    -H "Origin: http://$(hostname):5476" \
    -H "Content-Type: application/json" \
    -d '{"task": "...", "agent": "ghost"}'
  ```
- [x] 5.2 For steer/continue/status calls, cookie auth also works. Omit
  `X-Internal-Secret` from all REST call examples (cookie-only is consistent and simpler).

## 6. Unit tests

- [x] 6.1 `_mint_internal_cookie` parses cookie from well-formed curl output
- [x] 6.2 `_mint_internal_cookie` returns None on exec failure (logs WARNING)
- [x] 6.3 `_finish_crew_setup` passes internal cookie (from `_mint_internal_cookie`)
  to `_write_dashboard_cookie` and stores `internal_cookie` in registry
- [x] 6.4 `_refresh_cookie` calls `_mint_internal_cookie` and stores result in registry
- [x] 6.5 `_dispatch_captain_checkin` reads `internal_cookie` from registry, skips
  write (not a fresh mint) when absent

## 7. Integration test

- [ ] 7.1 Launch fresh crew; verify `.dashboard_cookie` exists with 600 perms
- [ ] 7.2 From inside container: `curl ... -H "Cookie: mc_token_5476=..." /api/spawn`
  → `{"status":"spawned"}` (no IP mismatch)
- [ ] 7.3 Ghost dispatched into member slot spawns child Ghost via cookie → success
- [ ] 7.4 Captain SDD order: Raven dispatches Ghost successfully
- [ ] 7.5 Commit and push on `release/0.6.0`
- [ ] 7.6 Bump adjutant submodule, deploy to starport
- [ ] 7.7 Smoke test: specky SDD order → Raven → Ghost spawned, implementation runs
