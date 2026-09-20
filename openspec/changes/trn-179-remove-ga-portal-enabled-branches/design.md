## Context

See proposal.md — Why.

Two spec files contain stale `GA_PORTAL_ENABLED` conditional branches:

**`openspec/specs/transport/dashboard-auth/spec.md`** — contains `WHEN GA_PORTAL_ENABLED=false`
(unauthenticated dashboard fallback) and `WHEN GA_PORTAL_ENABLED=true` guards around
the `forward_auth` requirements. The `caddy-proxy` spec already states
`GA_PORTAL_ENABLED` is removed and SHALL NOT be read, which directly contradicts
`dashboard-auth`.

**`openspec/specs/transport/tls/spec.md`** — contains `WHEN GA_PORTAL_ENABLED=false`
(direct TLS via `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE`) and `WHEN GA_PORTAL_ENABLED=true`
guards around the Caddy TLS path. Since TRN-103, Caddy is the only TLS path.

The `caddy-proxy` spec is already correct (authoritative post-TRN-103). The two
affected specs need to be brought in line with it.

## Goals / Non-Goals

**Goals**
- Remove all `GA_PORTAL_ENABLED` conditional branches from `dashboard-auth/spec.md`
  and `tls/spec.md`
- The remaining requirements MUST accurately describe the actual 0.6.0 behaviour
- `caddy-proxy/spec.md` is the reference — the edits must be consistent with it

**Non-Goals**
- Changing `caddy-proxy/spec.md` (already correct)
- Any code changes
- Removing `GA_PORTAL_ENABLED` references from docs or config examples (separate concern)

## Decisions

**Edit the main specs directly (not via delta specs).**
These are corrections to already-implemented specs, not new requirements. The `skip_specs`
flag is set; no change delta files are needed or appropriate.

**Collapse to unconditional requirements.**
Remove the `WHEN` guards entirely. The resulting requirements apply unconditionally,
matching the actual codebase state.

**Preserve the `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` note in tls/spec.md?**
No — those env vars are only meaningful when Caddy is absent (the old
`GA_PORTAL_ENABLED=false` path). The transport no longer has a direct TLS path.
Remove them from the spec entirely.

## Risks / Trade-offs

[Risk] An agent reads the corrected spec and tries to remove `GA_TLS_CERTFILE` code
that may still exist in `config.py` or `server.py` →
Mitigation: The spec correction is scoped to spec files only. A follow-up audit
change (TRN-x) can clean up config if the vars are genuinely unused.

## Migration Plan

Spec-only edits. No code or deployment changes needed.
