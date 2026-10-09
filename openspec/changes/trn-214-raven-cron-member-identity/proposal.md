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

The transport uses cookie auth and can spawn freely. Crew members have no access to the
cookie — they only have `.local_secret` for `X-Internal-Secret`.

**Empirical confirmation:** Ghost dispatched into `member-ghost` slot, sent
`X-Internal-Secret` + `X-Session-Key` + empty `X-Session-Token` → `member_identity_unavailable`.

## Fix — inject the dashboard cookie into all crew members

The dashboard cookie (`mc_token_5476=<value>`) gives any process inside the container the
same authority as the dashboard owner. The transport already mints and holds this cookie
(`_mint_cookie` → `crew["cookie"]`). Writing it to a known path in the container makes it
available to all crew members for spawning.

**Standardised pattern** (parallel to `.local_secret`):

```
/home/kirocrew/.kiro/crew/.local_secret      → X-Internal-Secret (already exists, gateway-owned)
/home/kirocrew/.kiro/crew/.dashboard_cookie  → Cookie: mc_token_5476=<value> (new, transport-written)
```

Any crew member that needs to spawn reads `.dashboard_cookie` and uses:
```
Cookie: mc_token_5476=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)
```
The gateway treats this as the dashboard owner — no attestation required.

**Written at launch, refreshed on Captain dispatch/steer.** Cookie TTL is 24h; the
transport refreshes it each time it dispatches or steers Raven, keeping it current.

## What changes

**`transport/lifecycle.py` — `_finish_crew_setup`**: after minting the cookie, write it
to `/home/kirocrew/.kiro/crew/.dashboard_cookie` inside the container via `podman exec`.

**`transport/lifecycle.py` — `_ensure_crew_running`** (restart path): also refresh
`.dashboard_cookie` when the crew restarts and a new cookie is minted.

**`transport/server.py` — `_dispatch_captain_checkin`**: refresh `.dashboard_cookie`
before each Raven dispatch (cookie may have aged).

**`transport/server.py` — `_steer_captain_checkin`**: refresh `.dashboard_cookie`
before each steer.

**`transport/captain.py` — `_RAVEN_GATEWAY_ORIENTATION`**: update spawn auth instructions
to use the cookie header alongside the local secret:
```
X-Internal-Secret: $(cat /home/kirocrew/.kiro/crew/.local_secret)
Cookie: mc_token_5476=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)
```
Note: `X-Session-Key` header is no longer needed for spawning with cookie auth.

**`academy/agents/*.json`** — no changes needed; cookie auth works from the shell tool
without any tool list changes.

## What does NOT change

- `schedule()` tool — unaffected
- The captain mailbox, fire_immediately, API surface — unchanged
- Raven's tool list (`["read", "grep", "glob", "shell"]`) — unchanged
- The dispatch+steer architecture from Stage 1 — unchanged
