# TRN-214: Raven cron session lacks member identity on 0.8.0

## Problem

The entire Captain workflow (sdd, indy, free-form orders) is broken on KiroCrew 0.8.0.
Crew members dispatched by Captain cannot spawn sub-agents — all spawn attempts return
`member_identity_unavailable` (HTTP 409).

## Root cause (confirmed via source trace + empirical tests)

**Stage 1 (implemented):** Crons created via `POST /api/crons` have no `execution_context`.
Fixed by replacing Captain cron with dispatch+steer loop so Raven runs in
`dashboard:member-raven`.

**Stage 2 (this change):** Even with Raven in her member slot, downstream spawn calls
fail. The gateway has two auth paths for `POST /api/spawn`:

```
Cookie auth  (Cookie: mc_token_5476=<value>)  → dashboard owner path → no attestation → WORKS
X-Internal-Secret + X-Session-Key             → internal_auth path   → attestation required → FAILS
```

The attestation check (`session_key_is_attested()`) requires either Unix socket peer
verification OR a signed `X-Session-Token` header. Neither is available to crew members
calling the REST API from shell:
- Unix socket: `/proc` ancestry resolves to the parent session, causing `peer_session_mismatch`
- `X-Session-Token` (`KIROCREW_STUB_SESSION_TOKEN`): NOT present in the agent's shell
  environment — confirmed by empirical test with Ghost dispatched into member slot
- `kirocrew spawn run` CLI: same `member_identity_unavailable` — uses identical internal_auth
  path, confirmed by live investigation in 0.8.0

Cookie auth is the only viable path. But the cookie is IP-bound to whoever does the
`GET /?token=...` exchange: currently `_mint_cookie` does that exchange from the transport
host, so the cookie is bound to the transport's IP. Requests from inside the container
(loopback) get `403 IP mismatch`.

**Empirical confirmation:** Cookie minted via transport host → `403 IP mismatch` from inside
container. Cookie minted by doing the exchange from inside the container → `{"status": "spawned"}`.

## Fix — mint an internal cookie from inside the container

Change `_mint_cookie` to do the token exchange step (`GET /?token=...`) from inside the
container via `podman exec curl` rather than from the transport host. This binds the
resulting cookie to `127.0.0.1` (loopback), not the transport's IP.

The cookie written to `.dashboard_cookie` is then usable by any process inside the
container — crew members, agents, subagents — without IP restriction.

**Two-step mint (both inside the container):**
1. `kirocrew token --ttl 24h` → URL with raw token (already runs inside via podman exec)
2. `curl http://localhost:5476/?token=<token>` inside the container → Set-Cookie response
   → parse `mc_token_5476=<value>` from response headers

**Standardised pattern** (parallel to `.local_secret`):
```
/home/kirocrew/.kiro/crew/.local_secret      → X-Internal-Secret (gateway-owned)
/home/kirocrew/.kiro/crew/.dashboard_cookie  → Cookie: mc_token_5476=<value> (transport-written)
```

Any crew member reads `.dashboard_cookie` and spawns with:
```bash
COOKIE=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)
curl -s -X POST http://localhost:5476/api/spawn \
  -H "Cookie: mc_token_5476=$COOKIE" \
  -H "Content-Type: application/json" \
  -d '{"task": "...", "agent": "ghost"}'
```
Note: `X-Internal-Secret` is NOT needed alongside the cookie — it would route to
`internal_auth` and ignore the cookie. Cookie alone (with `Origin`) is sufficient.

**Written at launch, refreshed on Captain dispatch/steer.** Cookie TTL is 24h.

## What changes

**`transport/lifecycle.py` — `_mint_cookie`**: change the token exchange step to run
`curl http://localhost:{CREW_GATEWAY_PORT}/?token={token}` via `podman exec` inside the
container, parsing `Set-Cookie` from the curl output. The `kirocrew token` step is unchanged.
This is a contained change — `_mint_cookie` signature and return type are unchanged.

**`transport/lifecycle.py` — `_write_dashboard_cookie`**: helper already added; no change.

**`transport/lifecycle.py` — `_finish_crew_setup`**: already calls `_write_dashboard_cookie`
after `_mint_cookie`; no change needed once `_mint_cookie` produces the right cookie.

**`transport/lifecycle.py` — `_ensure_crew_running`**: same — already refreshes.

**`transport/server.py` — `_dispatch_captain_checkin` / `_steer_captain_checkin`**: already
refresh `.dashboard_cookie`; no change needed.

**`transport/captain.py` — `_RAVEN_GATEWAY_ORIENTATION`**: update spawn auth instructions
to use cookie-only (no `X-Internal-Secret`, no `X-Session-Key`):
```bash
COOKIE=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)
curl -s -X POST http://localhost:5476/api/spawn \
  -H "Cookie: mc_token_5476=$COOKIE" \
  -H "Origin: http://$(hostname):5476" \
  -H "Content-Type: application/json" \
  -d '{"task": "...", "agent": "ghost"}'
```

## What does NOT change

- `schedule()` tool — unaffected
- The captain mailbox, fire_immediately, API surface — unchanged
- Raven's tool list (`["read", "grep", "glob", "shell"]`) — unchanged
- The dispatch+steer architecture from Stage 1 — unchanged
- `_mint_cookie` signature, callers, and the transport's own `crew["cookie"]` — unchanged
