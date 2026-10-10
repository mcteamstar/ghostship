# Design: TRN-214 Stage 2 — Internal Cookie Mint

See proposal.md for root cause and Stage 1 history.

## Context

`_mint_cookie(podman, container, crew_url)` currently does two things:
1. `podman exec` → `kirocrew token --ttl 24h` → parses `?token=<jwt>` from output
2. `_http.get(f"{crew_url}/?token={token}")` → exchange from transport host → parses `Set-Cookie`

Step 2 is done from the transport host's IP. The gateway's `token_auth.py` binds the
resulting session cookie to that IP via `bind_token_ip(token, request.remote)`. Any
subsequent request using that cookie must come from the same IP — requests from inside
the container (loopback `127.0.0.1`) get `403 IP mismatch`.

**Fix:** add `_mint_internal_cookie(podman, container)` that runs step 2 from inside
the container via `podman exec curl`. The resulting cookie is bound to `127.0.0.1` and
usable by any process inside without IP restriction.

`_mint_cookie` is **not changed** — the transport's own `crew["cookie"]` continues to
bind to the bridge IP, which is correct for transport→gateway calls.

## Architecture

```
Two cookies in play:
  crew["cookie"]        — minted by _mint_cookie (exchange from transport host)
                          bound to bridge IP, used by transport for _crew_api calls
  .dashboard_cookie     — minted by _mint_internal_cookie (exchange from inside)
                          bound to 127.0.0.1, used by crew members for spawn calls

_mint_internal_cookie (new):
  1. podman exec kirocrew token --ttl 24h → parse ?token=<jwt>
  2. podman exec curl -si "http://localhost:5476/?token=<jwt>" → parse Set-Cookie
  return mc_token_5476=<value> or None

_finish_crew_setup:
  cookie = _mint_cookie(...)                           # external, for crew["cookie"]
  internal = _mint_internal_cookie(podman, container)  # internal, for .dashboard_cookie
  _write_dashboard_cookie(podman, container, internal) if internal else log WARNING

_refresh_cookie (extended):
  new_cookie = _mint_cookie(...)                       # refresh external
  new_internal = _mint_internal_cookie(...)            # refresh internal together
  _write_dashboard_cookie(podman, container, new_internal) if new_internal
  # Single refresh path covers all crews (Captain or not, idle or active)

_ensure_crew_running restart path:
  # _refresh_cookie is already called here via the restart sequence;
  # no separate internal refresh needed once _refresh_cookie covers both.

_dispatch_captain_checkin / _steer_captain_checkin:
  # No cookie minting here — _refresh_cookie handles staleness.
  # These keep the _write_dashboard_cookie call as a belt-and-suspenders refresh
  # using the ALREADY-MINTED internal cookie from registry (not a fresh mint).
  # If no internal cookie in registry, skip silently — _refresh_cookie will fix it.

Crew member spawn call (all four endpoints):
  COOKIE=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)
  curl -s -X POST http://localhost:5476/api/spawn \
    -H "Cookie: mc_token_5476=$COOKIE" \
    -H "Origin: http://$(hostname):5476" \
    -H "Content-Type: application/json" \
    -d '{"task": "...", "agent": "ghost"}'
```

## Decisions

**D1: Add `_mint_internal_cookie` as a separate helper, leave `_mint_cookie` unchanged.**

`_mint_cookie` signature, callers, and the transport's `crew["cookie"]` are all
unchanged. `_mint_internal_cookie` is the new path for the internal-bound cookie only.

**D2: Run the exchange from inside the container via `podman exec curl -si`.**

`curl` is present in the spec-ops image (confirmed). `-si` returns response headers
including `Set-Cookie` without progress output. The exchange hits `localhost:5476`
from inside, so `request.remote` resolves to `127.0.0.1`.

**D3: `_refresh_cookie` is the single refresh path for both cookies.**

It already runs on health-probe cycle and at crew restart. Extending it to also call
`_mint_internal_cookie` and `_write_dashboard_cookie` covers all cases — Captain crews,
non-Captain crews, idle restarts. No parallel refresh machinery needed.

**D4: Store the internal cookie value in the registry alongside `crew["cookie"]`.**

Key: `internal_cookie`. This lets `_dispatch_captain_checkin` / `_steer_captain_checkin`
write the already-minted value to `.dashboard_cookie` without triggering a fresh mint
on every Captain tick. If `internal_cookie` is absent (old registry), fall back to
skipping the write (next `_refresh_cookie` will populate it).

**D5: Cookie-only auth for ALL four spawn REST endpoints.**

Confirmed in source (`_spawn_scope_refusal`): cookie auth (no `internal_auth`) is
admitted unconditionally on `POST /api/spawn`, `POST /api/spawn/{id}/steer`,
`POST /api/spawn/{id}/continue`. `GET /api/spawn/{id}` has no auth at all.

Sending `X-Internal-Secret` alongside the cookie routes to `internal_auth`, which
IGNORES the cookie and hits the attestation wall. Cookie-only is correct.
`X-Internal-Secret` is NOT needed for any of Raven's REST calls when using cookie auth.

**D6: `Origin: http://$(hostname):5476` required on spawn calls.**

Without an `Origin` header some gateway middleware rejects the request. `$(hostname)`
inside the container resolves to the container name (e.g. `gs-demo`), matching what
the transport sends in `_crew_api`.

## Risks / Trade-offs

**[Risk] Two cookies in flight** → Different IPs, different use cases. No overlap.
The internal cookie is never used by the transport; the external cookie is never
written to `.dashboard_cookie`.

**[Risk] 24h TTL expiry** → Handled by `_refresh_cookie` (same cycle as external
cookie refresh). No separate expiry handling needed.

**[Risk] `internal_cookie` absent in old registry rows** → Graceful skip at dispatch/steer;
next `_refresh_cookie` writes it. No hard failure.

**[Risk] `curl` availability** → Confirmed in spec-ops image. If absent in a custom
image, `_mint_internal_cookie` returns None and `.dashboard_cookie` is not written —
crew members fall back to the existing `member_identity_unavailable` behaviour, not
something worse.
