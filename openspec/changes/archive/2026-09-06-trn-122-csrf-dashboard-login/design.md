## Context

`POST /dashboard-login` is a public route (no bearer token required) that validates `ga_api_key` via `hmac.compare_digest` and issues a `gs_session` cookie. The login form is served by `_handle_login_ui` (GET `/login-ui`) and rendered as a self-contained HTML string — no template engine, no session middleware, no framework-level CSRF support.

The existing `_gs_session_store` and `_gs_session_issue` pattern (module-level dict + `threading.Lock`) shows the project's idiom for lightweight in-process state. The `secrets` module is already imported.

See `proposal.md – Why` for motivation.

## Goals / Non-Goals

**Goals:**
- Block form submissions that do not carry the server's own token (cross-origin CSRF attacks)
- Token is cheap: generated once per process, no per-session state, no DB, no cookie
- Comparison is constant-time to match the project's existing `hmac.compare_digest` usage

**Non-Goals:**
- Per-session or per-request token rotation (synchroniser-token pattern) — overkill for a single-form endpoint behind `SameSite=Lax` cookies
- CSRF protection for any endpoint other than `POST /dashboard-login`
- Changes to the `gs_session` cookie attributes or the dashboard-auth forward-auth flow

## Decisions

### D1 — Single startup token, not per-request

**Decision**: generate `_dashboard_csrf_token = secrets.token_hex(32)` at module load, hold it for the process lifetime.

**Rationale**: the login form is the only state-mutating endpoint that is both public and browser-facing. A fixed token is indistinguishable from a per-request token to a legitimate browser client (it reads from the form it just fetched), while eliminating any server-side state and avoiding the double-submit-cookie complexity. The token is invalidated on transport restart, which is the right granularity.

**Alternative considered**: per-request nonce stored in a short-lived dict. Adds bookkeeping and lock contention with no practical security gain here.

### D2 — 403 on mismatch, not 400 or 401

**Decision**: return `Response(status_code=403)` when the CSRF check fails.

**Rationale**: 403 is the conventional status for a rejected CSRF submission (request understood, forbidden). 400 would conflate CSRF rejection with malformed input; 401 would conflate it with a missing API key.

### D3 — Embed token in existing form, not a separate endpoint

**Decision**: add `<input type="hidden" name="csrf_token" value="{token}">` to the `_handle_login_ui` HTML string. No new route.

**Rationale**: the form already renders as an f-string with HTML-encoded values. The existing `_security.encode_html_attr` call pattern (used for `next_url_escaped`) can be applied to the token for defence-in-depth, even though hex output is already safe.

### D4 — CSRF check runs before API-key check

**Decision**: in `_handle_dashboard_login_post`, the CSRF comparison is the first body-read action, before `hmac.compare_digest(provided, GA_API_KEY)`.

**Rationale**: fail-fast on forged requests without touching the API key comparison path.

## Risks / Trade-offs

- **Process restart invalidates the token** → any open login form becomes stale after a transport restart and returns 403. Mitigation: the form auto-submits via JS; a stale tab is an acceptable UX edge case, and the user can reload to get a fresh token. No additional handling needed.
- **`_dashboard_csrf_token` is module-level, readable by tests** → tests can patch or read it directly, which is consistent with how `GA_API_KEY` is tested today.

## Migration Plan

Drop-in: no data migration, no config change, no Caddy rule update. The hidden field is transparent to the existing JS `fetch` path in `_handle_login_ui` because `new FormData(f)` picks up all `<input>` elements including hidden ones.

Rollback: revert the two function changes and the module-level constant.
