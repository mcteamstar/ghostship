## Context

Three targeted bug fixes in `transport/server.py`. All three were found by stevemac007 during migration assessment work. See proposal.md for motivation.

Relevant functions:
- `_read_auth_from_crew` (line ~2663) — reads `auth_kv` rows from a crew's kiro-cli SQLite DB
- `_idle_monitor` (line ~4954) — background thread that stops idle crew containers
- `_handle_crew_api_proxy` (line ~493) — reverse-proxies REST calls to the crew gateway

## Goals / Non-Goals

**Goals:** Fix the three bugs with minimal, surgical changes. Add regression tests for each.

**Non-Goals:** Refactor the surrounding logic, change any public-facing API behaviour, or address TRN-71 modularisation concerns.

## Decisions

### Bug 1: Auth row token check

**Decision:** Check that at least one `auth_kv` row has a non-empty `value` field that looks like a credential (non-empty string), rather than just checking `if rows:`.

The kiro-cli device flow writes a registration row early (before user approval) with minimal data. A credential-complete row has a `value` field containing a serialised token. Checking `value` is non-empty and non-null distinguishes the two states without needing to parse the token format — which would couple us to kiro-cli internals.

Alternative considered: check for a specific key name (e.g. `access_token`). Rejected — key names could change across kiro-cli versions.

### Bug 2: Idle monitor 403 handling

**Decision:** Extend `if r.status_code == 401:` to `if r.status_code in (401, 403):` in the inline recovery branch of `_idle_monitor`.

The existing `_crew_api_with_recovery` helper already handles `400/401/403`, but `_idle_monitor` has its own inline cookie-refresh path that only checked `401`. A 403 (CSRF mismatch after cookie expiry) previously caused fail-open — the crew was assumed to have active tasks and never stopped. This is the root cause of the 17-hour idle VM observed in the field.

Note: TRN-71 (modularisation) will eventually remove this duplication by making the idle monitor use `_crew_api_with_recovery` directly (finding F11). This fix is a safe interim patch.

### Bug 3: Cookie header collision in API proxy

**Decision:** Add `and k.lower() != "cookie"` to the header filter in `_handle_crew_api_proxy`, matching the existing `k.lower() != "host"` pattern.

Starlette normalises inbound headers to lowercase. The proxy builds `forward_headers` by filtering out `host`, then injects `Cookie: mc_token_5476=...` (titlecase). If the inbound request included a `cookie` header (e.g. from a browser), both the lowercase `cookie` and the injected titlecase `Cookie` survive — HTTP allows duplicate header names but the gateway interprets the first one and rejects with 403. Stripping at filter time is the cleanest fix.

## Risks / Trade-offs

- Bug 1: If a future kiro-cli version stores credentials differently (e.g. empty `value` for a valid row), the check could false-negative. Mitigated by only checking non-empty, not checking specific content.
- Bug 2: The inline recovery in `_idle_monitor` remains duplicated until TRN-71. Acceptable short-term.
- Bug 3: Any legitimate inbound `Cookie` header is now stripped before forwarding. The API proxy is only used for internal gateway calls where the transport injects its own session cookie — no legitimate use case for a caller-supplied cookie here.

## Migration Plan

No migration needed. All three changes are backward-compatible. The token format in `auth_kv` is unchanged — only the validation is tightened.
