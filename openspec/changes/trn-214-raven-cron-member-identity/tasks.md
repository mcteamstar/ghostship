# Tasks: TRN-214 Stage 2 — Cookie Injection

Stage 1 (dispatch+steer loop) is already implemented and deployed.
Stage 2 adds the cookie injection that enables crew members to spawn sub-agents.

## 0. Extract `_write_dashboard_cookie` helper

- [x] 0.1 In `transport/lifecycle.py`, add a `_write_dashboard_cookie(podman, container, cookie)` helper that does the podman exec write + chmod 600, logs DEBUG on success, WARNING on failure, and returns bool. Four call sites will use it — extract once rather than inline four times.

## 1. Write `.dashboard_cookie` at crew setup

- [x] 1.1 In `transport/lifecycle.py:_finish_crew_setup`, after `cookie = _mint_cookie(...)`,
  write the cookie value to `/home/kirocrew/.kiro/crew/.dashboard_cookie` via `podman exec`:
  `python3 -c "open('/home/kirocrew/.kiro/crew/.dashboard_cookie','w').write(COOKIE); import os; os.chmod(..., 0o600)"`
- [x] 1.2 Log the write at DEBUG level; log a WARNING on failure (non-fatal)
- [x] 1.3 In `_ensure_crew_running` (the restart path), also write `.dashboard_cookie`
  after a cookie is minted/refreshed for a restarted crew

## 2. Refresh `.dashboard_cookie` on Captain dispatch/steer

- [x] 2.1 In `transport/server.py:_dispatch_captain_checkin`, write current `crew["cookie"]`
  to `.dashboard_cookie` before spawning Raven
- [x] 2.2 In `transport/server.py:_steer_captain_checkin`, same refresh before continuing

## 3. Update `_RAVEN_GATEWAY_ORIENTATION`

- [x] 3.1 In `transport/captain.py:_RAVEN_GATEWAY_ORIENTATION`, update ALL REST call
  auth instructions to use cookie auth:
  - `X-Internal-Secret: $(cat /home/kirocrew/.kiro/crew/.local_secret)`
  - `Cookie: mc_token_5476=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)`
- [x] 3.2 Remove `X-Session-Key` from all REST call instructions — cookie auth (dashboard
  owner) is admitted without a session key on all four spawn endpoints:
  `POST /api/spawn`, `GET /api/spawn/{id}`, `POST /api/spawn/{id}/steer`,
  `POST /api/spawn/{id}/continue`
- [x] 3.3 Note: `GET /api/spawn/{id}` has no auth check at all — include for completeness
  but no header changes needed there

## 4. Unit tests

- [x] 4.1 `_finish_crew_setup` writes `.dashboard_cookie` via podman exec after cookie mint
- [x] 4.2 `.dashboard_cookie` write failure is non-fatal (logs warning, doesn't abort setup)
- [x] 4.3 `_dispatch_captain_checkin` writes `.dashboard_cookie` before dispatch
- [x] 4.4 `_steer_captain_checkin` writes `.dashboard_cookie` before continue

## 5. Integration test

- [ ] 5.1 Launch fresh crew, verify `.dashboard_cookie` exists in container after launch
- [ ] 5.2 Dispatch Ghost into member slot; have him spawn a child Ghost using cookie auth
  — verify child spawns successfully (no `member_identity_unavailable`)
- [ ] 5.3 Issue a captain SDD order; verify Raven dispatches Ghost successfully
- [ ] 5.4 Commit and push on `release/0.6.0`
- [ ] 5.5 Bump adjutant submodule, deploy to starport
- [ ] 5.6 Run full smoke test: specky SDD order → Raven → Ghost spawned, implementation runs
