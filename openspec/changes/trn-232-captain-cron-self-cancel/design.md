# Design

## Context

See proposal.md for motivation.

The captain schedule is created and managed entirely by the transport's schedule
registry (`_captain_do_order`, `_captain_do_stop`, `_captain_monitor`). From inside the
crew container, `kirocrew cron list` queries the KiroCrew gateway's cron registry — a
completely separate system. The transport schedule has no presence there, so
`kirocrew cron pause "captain"` silently finds nothing. `_RAVEN_SELF_CANCEL` today
instructs Raven to use `kirocrew cron pause`, which is why self-cancel has never worked.

The transport already has:
- `_captain_do_stop(crew_id)` — disables the captain schedule entry in the registry
- `captain(action="stop")` MCP tool — the external-facing wrapper
- Dashboard cookie auth in `BearerAuthMiddleware` — the same credential path Raven uses
  for spawn calls (`/home/kirocrew/.kiro/crew/.dashboard_cookie`)

## Goals / Non-Goals

**Goals:**
- Add a transport REST endpoint callable from inside the crew that stops the captain schedule
- Update `_RAVEN_SELF_CANCEL` to use this endpoint
- Keep the existing `captain(action="stop")` MCP tool unchanged

**Non-Goals:**
- Changing how the captain schedule is stored or managed
- Exposing any other schedule management operations to crew-internal callers
- Any change to how `captain(action="stop")` works externally

## Decisions

### D1 — New route `POST /crews/{crew_id}/captain/stop`

Reuse `_captain_do_stop(crew_id)` as the underlying implementation. The new handler
validates the dashboard cookie, calls `_captain_do_stop`, and returns a small JSON
response. No new state, no new concepts.

**Path choice:** `/crews/{crew_id}/captain/stop` fits the existing crew-scoped URL
pattern (`/crews/{crew_id}/...`). Consistent with how `_dispatch_captain_checkin` and
`_steer_captain_checkin` target crew-specific state.

**Auth:** Dashboard cookie (`mc_token_{port}`) via the existing
`BearerAuthMiddleware._dispatch_public_route` exemption pattern. This endpoint must NOT
require `ga-api-key` Bearer auth — the cookie is all that is available inside the
container. Add it to the public-route exemption list alongside the login routes.

**Alternative considered:** Have Raven write a sentinel file that the captain monitor
reads. Rejected — asynchronous, adds polling lag, and introduces a new side-channel
convention when a clean HTTP call is already the established pattern for crew→transport
communication.

### D2 — Update `_RAVEN_SELF_CANCEL`

Replace the `kirocrew cron pause` instruction with a curl call to the new endpoint:

```bash
crew_id="$KIROCREW_CREW_ID"
cookie=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)
curl -s -X POST "http://localhost:64057/crews/${crew_id}/captain/stop" \
  -H "Cookie: mc_token_5476=${cookie}" \
  -H "Origin: $(echo $KIROCREW_CORS_ORIGINS | cut -d, -f1)"
```

Confirm success by checking the response contains `"stopped"` — not by calling
`kirocrew cron list`, which will still show nothing (by design).

### D3 — Response codes

- `200 {"status": "stopped"}` — success
- `400 {"error": "captain already stopped"}` — already disabled (idempotent-safe retry)
- `404 {"error": "no captain entry for crew <id>"}` — no entry exists

400 on already-stopped (rather than 200) keeps the behaviour consistent with `_captain_do_stop`'s existing logic and gives Raven a clear signal that the stop was a no-op.

## Risks / Trade-offs

**[Risk] Cookie expires between crew launch and self-cancel.**
→ Mitigation: The transport refreshes `.dashboard_cookie` on each captain dispatch and
steer (existing behaviour from TRN-214). By the time Raven reaches self-cancel, the
cookie was written within the last check-in cycle — well within any session TTL.

**[Risk] CORS origin header mismatch causes 403.**
→ Mitigation: `_RAVEN_SELF_CANCEL` uses `$KIROCREW_CORS_ORIGINS` (same pattern as spawn
calls) to derive the origin. This is already established and tested by the spawn path.

## Migration Plan

1. Add the route in a single commit alongside the `_RAVEN_SELF_CANCEL` update.
2. No migration of existing crews — the next check-in cycle picks up the new instruction.
3. Crews already completed that are stuck looping will self-cancel on the next Raven
   check-in once upgraded.

## Open Questions

None.
