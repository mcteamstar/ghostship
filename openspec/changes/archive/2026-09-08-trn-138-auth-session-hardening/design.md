## Context

See proposal.md. Five auth/session gaps from the independent review. All changes are in existing well-understood code paths.

## Goals / Non-Goals

**Goals:**
- CSRF on logout (consistent with login)
- Server-side redirect fix (return sanitised `next` in JSON, redirect from that)
- `GA_PORTAL_SESSION_TTL_SECS` actually injected into compose.yml
- Login throttle keyed on ASGI client IP, not XFF

**Non-Goals:**
- Redesigning the session store
- Persistent sessions across restarts
- CSRF token rotation strategy changes

## Decisions

**D1: CSRF on logout — reuse existing `_dashboard_csrf_token`**
The same process-lifetime CSRF token already embedded in the login form is the correct thing to check on logout. Logout is a state-changing POST; it should require the CSRF token in the request body or header.

**D2: Redirect fix — return `next` in JSON 200 body**
Current: JS reads `fd.get('next')` from the submitted FormData. Fix: server includes `{"next": sanitised_url}` in the JSON response; JS reads from `data.next`. This means the server's `_validate_next_url()` output is always the source of truth for the redirect target.

**D3: XFF — use ASGI client tuple for login throttle**
The login throttle in `_handle_dashboard_login_post` should use `request.client.host` (the actual TCP connection IP from ASGI) rather than XFF. XFF is still useful for logging/audit but should not gate security decisions. This is a targeted change to the login handler only — other rate-limit endpoints can be addressed separately.

**D4: `GA_PORTAL_SESSION_TTL_SECS` injection**
`install.sh` generates compose.yml with hardcoded env vars. Add `GA_PORTAL_SESSION_TTL_SECS` to the env block template, defaulting to `86400` if unset. This matches the pattern of other `GA_PORTAL_*` vars already injected.

**D5: Corrupt registry — structured error**
`_load_registry()` already raises on corrupt JSON. Callers at MCP tool entry points should catch `json.JSONDecodeError` (and the custom `RegistryError` if it exists) and return a structured `{"error": "..."}` response rather than letting it propagate as an unhandled exception.

## Risks / Trade-offs

- [Risk] CSRF on logout may break existing browser clients that POST to `/dashboard/logout` without a token. → Mitigation: the CSRF token is embedded in the login-UI page; any browser that used login also has the token. Direct API callers were never expected.
- [Risk] Using ASGI client IP breaks deployments where the transport is behind a trusted local proxy. → These deployments already have Caddy in front; Caddy's actual connection to the transport is the real IP anyway.

## Migration Plan

No data migration. All changes are request-handling logic. Deploy is a transport container restart.

## Open Questions

None.
