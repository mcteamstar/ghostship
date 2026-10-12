# Tasks

## 1. Transport endpoint — `POST /crews/{crew_id}/captain/stop`

- [x] 1.1 In `transport/server.py`, add `_handle_captain_stop_post(request, crew_id)`
      handler: validate dashboard cookie auth, call `_captain_do_stop(crew_id)`, return
      `200 {"status": "stopped"}` on success, `400 {"error": "captain already stopped"}`
      if already disabled, `404 {"error": "no captain entry for crew <id>"}` if no entry.
      Register the route `("POST", "/crews/{crew_id}/captain/stop")` in the route table
      alongside the existing captain routes. Verify: unit test passes (task 1.2).
- [x] 1.2 In `tests/unit/test_captain.py`, add tests for `_handle_captain_stop_post`:
      - Success: mock registry with an enabled entry → assert 200 `{"status": "stopped"}`
        and `_captain_do_stop` called.
      - Already stopped: mock registry with disabled entry → assert 400.
      - No entry: mock registry returning no captain entry → assert 404.
      - No auth: missing/invalid cookie → assert 401/403.
      Verify: `tests/run.sh --unit` passes.

## 2. Auth exemption

- [x] 2.1 In `transport/auth.py` (or wherever `BearerAuthMiddleware` exempts routes),
      add `/crews/*/captain/stop` (or the equivalent pattern) to the public-route
      exemption list so the endpoint accepts dashboard cookie auth without requiring
      `ga-api-key` Bearer auth. Verify: the new test in task 1.2 with no Bearer header
      passes without a 401 from the outer auth middleware.

## 3. Update `_RAVEN_SELF_CANCEL`

- [x] 3.1 In `transport/captain.py`, replace `_RAVEN_SELF_CANCEL` with the curl-based
      instruction that calls `POST http://localhost:64057/crews/${KIROCREW_CREW_ID}/captain/stop`
      using `Cookie: mc_token_5476=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)` and
      `Origin: $(echo $KIROCREW_CORS_ORIGINS | cut -d, -f1)`. Instruct Raven to treat a
      `200` response as success, `400` as already-stopped (also success), and `404`/any
      other status as a failure to report to the Admiral. Verify: the updated constant
      does not reference `kirocrew cron pause`; check with `grep -n "cron pause"
      transport/captain.py` → no output.

## 4. Update `openspec/specs/captain/spec.md`

- [x] 4.1 In `openspec/specs/captain/spec.md`, update the `{{RAVEN_SELF_CANCEL}}`
      placeholder requirement to state that the placeholder resolves to a curl call to
      `POST /crews/{crew_id}/captain/stop` on the transport, not `kirocrew cron pause`.
      Verify: `openspec validate --specs` passes.

## 5. Integration verification

- [x] 5.1 Run `tests/run.sh --unit` — must pass after all changes.
- [x] 5.2 Deploy to corsair and run a short SDD cycle (or stub it): confirm that when
      Raven completes and calls the self-cancel endpoint, the captain schedule entry is
      disabled and the crew idles normally. Alternatively, verify by checking
      `ghostship captain status <crew_id>` returns `enabled: false` after a natural
      SDD completion.

## Workflow follow-up

- Archive the change after tests pass and the live verification in task 5.2 is confirmed.
