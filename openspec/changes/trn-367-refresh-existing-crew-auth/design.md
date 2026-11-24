# Design

## Context

See proposal.md for motivation. Login-flow completion already injects refreshed credentials into matching running crews, while the wake path injects current flow credentials into stopped crews. Static credentials are container environment values and cannot be changed in place. Radar is a browser-facing service behind Caddy's session gate and already calls transport's secret-protected internal API.

## Goals / Non-Goals

**Goals:**
- Let operators retry credential injection for one crew using only its registry-assigned backend and profile.
- Give direct operator API clients and the Portal/Radar UI access to the same operation.
- Keep credentials out of browser requests, endpoint responses, and logs; report when recreation is required without restarting or deleting a crew.

**Non-Goals:**
- Add an MCP tool or let a driving agent refresh or choose credentials.
- Change a crew's backend, auth method, or credential profile. A refresh applies the credential currently assigned to the crew.
- Automatically restart or recreate crews, or change the credential login/logout flows.

## Decisions

### Share one refresh operation across two transport routes

Implement one transport operation and expose it through `POST /crews/{crew_id}/auth/refresh` for bearer-authenticated operator clients and `POST /internal/crews/{crew_id}/auth/refresh` for trusted portside callers. The public route uses the existing operator API auth and rejects browser `Origin` requests. The internal route uses `X-Transport-Token`, as Radar's other transport calls do. Both resolve auth from the crew's recorded backend/profile and return the same result shape. This keeps the Portal service from needing the operator bearer secret and prevents browser input from selecting or carrying credentials.

### Apply current flow credentials only to the selected running crew

Resolve the stored credential at request time and dispatch through the existing backend-specific injectors. Serialize the refresh with credential replacement/logout and recheck the selected profile before injection, so a concurrent credential change cannot restore stale auth. On success, clear Kiro's cached sign-in status when applicable. Injection failure is reported for that crew and does not stop or restart it. A stopped flow-auth crew returns `pending_on_wake`; the existing launcher will inject the current profile credential when it wakes.

### Detect static-credential mismatch without changing the container

For static methods, compare the stored method/value against the container's launch-time environment without returning or logging either value. Return `current` for a match and `recreate_required` for a mismatch. Do not attempt an in-place update or start/stop the crew. The response points to the existing workspace-preserving `evac`/recreate workflow documented in `docs/auth.md`.

### Make Radar a session-gated operator client

Add a per-crew action to the Radar detail panel. Radar exposes `POST /api/crews/{crew_id}/auth/refresh` and proxies it to the internal transport route with the mounted transport secret. Caddy's `/api/crews*` route already forwards to Radar after `forward_auth`; preserve that gate for the mutating request. Radar displays each safe transport outcome and does not hold or forward backend credential data. Direct automation uses the bearer-protected transport route.

### Keep lifetime guidance explicitly approximate

Update `docs/auth.md` with the ticket's observed estimates (about 10 days for Codex ChatGPT and about 90 days for Kiro Identity Center), state that provider/account settings vary, and describe how flow refresh and static replacement affect existing crews. These values are guidance, not expiry guarantees.

## Risks / Trade-offs

- **Credential changes while refresh is in flight** → Serialize with existing credential transactions and verify the current stored profile before injection.
- **Operator mistakes an API response for a successful static rotation** → Return a distinct `recreate_required` result with the established workspace-preserving recovery guidance; never silently claim the running container was updated.
- **Portal action is called without a browser session** → Keep it under Caddy's existing session gate; require `X-Transport-Token` on Radar-to-transport calls.
- **Provider session lifetime changes** → Label documented values as estimates and avoid presenting them as policy guarantees.

## Migration Plan

No registry migration or new secret is required. Additive API routes and the Radar control can ship with the normal Ghostship/Radar image update. Existing crews and stored credentials remain usable. Rollback removes the routes and UI control; credentials already injected into crew containers remain as they are, so rollback does not require workspace or auth cleanup.
