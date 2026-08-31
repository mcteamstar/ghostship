## Context

This is a retroactive documentation change, not new implementation work. `203c9f5` already shipped the fix directly to `release/0.2.2`, reusing TRN-55's `_sanitise_query_string` helper (`transport/server.py`) at the `SecurityHeadersMiddleware` redirect site (`transport/server.py:~1056`) instead of the original raw `qs.decode('latin-1')`. See proposal.md for why this has no prior paper trail.

## Goals / Non-Goals

**Goals:**
- Give the already-shipped fix a spec record, so `openspec validate` and future changes have a real requirement to check against instead of undocumented behavior.

**Non-Goals:**
- No code changes.
- No attempt to fully document `SecurityHeadersMiddleware`'s other responsibilities (HSTS, CSP, baseline headers, the plaintext-hit logging behavior) — those are real, shipped (TRN-70), and out of scope here since they weren't touched by `203c9f5`. A future change can extend the `security-headers` capability to cover them.

## Decisions

**Scope the new capability narrowly to what was actually changed**, rather than writing a broad `security-headers` spec covering everything the middleware does. Documenting untouched behavior here would overstate this change's actual scope and risks the requirements drifting from what `203c9f5` (or any single commit) can be checked against.

## Risks / Trade-offs

[The `security-headers` capability now exists but is incomplete relative to the real middleware] → Accepted; the Purpose section says so explicitly. Low risk — an incomplete spec is strictly better than no spec, and the gap is documented rather than hidden.

## Migration Plan

None — no code changes, single documentation commit, then sync/archive.
