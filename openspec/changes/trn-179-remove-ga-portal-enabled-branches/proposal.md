## Why

The specs for `dashboard-auth` and `tls` (`openspec/specs/transport/dashboard-auth/spec.md`
and `openspec/specs/transport/tls/spec.md`) still contain `GA_PORTAL_ENABLED=true/false`
conditional branches inherited from the pre-TRN-103 era when portal was opt-in. TRN-103
made `ga-portal` mandatory and removed the flag from the codebase entirely. The specs
are now factually wrong: they describe a two-mode world (`PORTAL_ENABLED=true` vs
`false`) that no longer exists. Any implementer reading them gets incorrect expectations.

## What Changes

- **`openspec/specs/transport/dashboard-auth/spec.md`** — remove the
  `WHEN GA_PORTAL_ENABLED=false` branch (unauthenticated dashboard fallback); collapse
  to a single unconditional requirement that Caddy `forward_auth` gates all dashboard
  traffic. Remove the `WHEN GA_PORTAL_ENABLED=true` guard — the condition is always true.
- **`openspec/specs/transport/tls/spec.md`** — remove the `WHEN GA_PORTAL_ENABLED=false`
  branch (`GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` direct TLS path); collapse to the single
  Caddy-owned TLS path. Remove the `WHEN GA_PORTAL_ENABLED=true` guard.
- No code changes — the flag is already absent from all Python source files.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
None in the delta-spec sense — these are corrections to already-implemented specs,
not new requirements. `skip_specs: true` is set; no delta spec files are needed.

## Impact

- `openspec/specs/transport/dashboard-auth/spec.md` — spec text changes only
- `openspec/specs/transport/tls/spec.md` — spec text changes only
- No code, config, or API changes
