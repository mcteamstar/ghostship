# Design: TRN-214 Stage 2 — Cookie Injection

See proposal.md for root cause and Stage 1 history.

## Context

The transport holds `crew["cookie"]` — the `mc_token_5476=<value>` dashboard session
cookie. This is minted by `_mint_cookie(podman, container, crew_url)` via
`kirocrew token --ttl 24h` inside the container, then exchanged for a session cookie.

The transport already uses this cookie for all its own gateway calls via `_crew_cookie(crew)`.
Writing it to `/home/kirocrew/.kiro/crew/.dashboard_cookie` makes it available to all
crew members via the shell tool.

## Architecture

```
At launch (_finish_crew_setup):
  cookie = crew["cookie"]  # already minted
  podman exec <container> python3 -c "
    open('/home/kirocrew/.kiro/crew/.dashboard_cookie','w').write(cookie)
    import os; os.chmod('/home/kirocrew/.kiro/crew/.dashboard_cookie', 0o600)
  "

At each Captain dispatch/steer:
  # Refresh in case cookie has aged (24h TTL)
  cookie = crew["cookie"]  # from registry (refreshed by _refresh_cookie if needed)
  write .dashboard_cookie with updated value

Crew member spawn call:
  SECRET=$(cat /home/kirocrew/.kiro/crew/.local_secret)
  COOKIE=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)
  curl -s -X POST http://localhost:5476/api/spawn \
    -H "X-Internal-Secret: $SECRET" \
    -H "Cookie: mc_token_5476=$COOKIE" \
    -H "Content-Type: application/json" \
    -d '{"task": "...", "agent": "ghost"}'
```

## Decisions

**D1: Write just the cookie value, not the full header.**

`.dashboard_cookie` stores the raw value (e.g. `abc123`). Callers construct
`Cookie: mc_token_5476=$(cat .dashboard_cookie)`. This keeps the port number
(`CREW_GATEWAY_PORT`) out of the file and lets callers assemble the correct
header without hardcoding it.

**D2: Write at `_finish_crew_setup`, refresh at dispatch/steer.**

`_finish_crew_setup` is the natural place — the cookie is already minted there.
The transport refreshes `crew["cookie"]` via `_refresh_cookie` when stale; we
piggyback on that by writing to the container whenever we have an up-to-date value.

**D3: `podman exec` write, same pattern as other container-side setup.**

Consistent with `_inject_auth`, `_patch_crew_config`, `_enroll_crew_members`.
The transport already has `podman.container_exec` for this pattern.

**D4: `chmod 600` on the file.**

Same permission as `.local_secret`. The `kirocrew` user can read it; no
world-readable credential sitting in the container.

**D5: Update `_RAVEN_GATEWAY_ORIENTATION` to use cookie auth, drop X-Session-Key for all REST calls.**

Cookie auth (dashboard owner path) is admitted without a session key on all four
spawn endpoints: `POST /api/spawn`, `GET /api/spawn/{id}` (no auth at all),
`POST /api/spawn/{id}/steer`, and `POST /api/spawn/{id}/continue`. Confirmed in
`messaging.py:_spawn_scope_refusal`: `if request.get("internal_auth") is not True: return None`
— the dashboard owner is passed through unconditionally.

`X-Session-Key` should not be sent alongside a cookie — it would trigger the
`internal_auth` path instead of the dashboard owner path.

## Risks / Trade-offs

**[Risk] Cookie expires between refresh and use** → 24h TTL. Refresh happens at each
Captain fire (e.g. every hour). For non-Captain spawns from Ghost/Spectre/etc., the
cookie is written at launch and valid for 24h. A crew idle >24h would have a stale
cookie. Mitigation: `_ensure_crew_running` also refreshes the cookie and writes the file.

**[Risk] `.dashboard_cookie` readable by any process in the container** → Same risk as
`.local_secret`. Container = trusted boundary in KiroCrew's model. chmod 600 limits
it to the kirocrew user.

**[Risk] Sandbox visibility** → `.local_secret` is in `_CREW_CHILD_WITHHELD_LEAVES`
(not readable by sandboxed child harnesses). `.dashboard_cookie` may face the same
restriction. However, crew members using `shell` tool are NOT sandboxed foreign
harnesses — they're the kirocrew process's own shell. The sandbox restriction applies
to child harnesses (e.g. a second kiro-cli instance), not the primary agent shell.
Mitigation: test confirms cookie is readable from shell tool before declaring done.

## Migration

1. Deploy new transport — existing crews get `.dashboard_cookie` written on next
   `_ensure_crew_running` call. No crew image rebuild needed.
2. Existing Captain entries continue to work — next steer writes the cookie.
3. No rollback risk: if cookie write fails, spawn calls fall back to the existing
   `member_identity_unavailable` behaviour, not something worse.
