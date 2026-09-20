## 1. Fix dashboard-auth spec

- [ ] 1.1 Read `openspec/specs/transport/dashboard-auth/spec.md` and `openspec/specs/transport/caddy-proxy/spec.md` in full before editing
- [ ] 1.2 Remove the `WHEN GA_PORTAL_ENABLED=false` branch from `dashboard-auth/spec.md` (unauthenticated dashboard fallback)
- [ ] 1.3 Remove the `WHEN GA_PORTAL_ENABLED=true` guard — restate the `forward_auth` requirements as unconditional
- [ ] 1.4 Verify the remaining requirements are consistent with `caddy-proxy/spec.md` (no contradictions)

## 2. Fix TLS spec

- [ ] 2.1 Read `openspec/specs/transport/tls/spec.md` in full before editing
- [ ] 2.2 Remove the `WHEN GA_PORTAL_ENABLED=false` branch (direct TLS via `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE`)
- [ ] 2.3 Remove the `WHEN GA_PORTAL_ENABLED=true` guard — restate the Caddy TLS requirements as unconditional
- [ ] 2.4 Remove references to `GA_TLS_CERTFILE` and `GA_TLS_KEYFILE` from the spec body (these belong to the removed direct TLS path)

## 3. Verify

- [ ] 3.1 Confirm neither spec file contains the string `GA_PORTAL_ENABLED`
- [ ] 3.2 Run `openspec validate --specs` and confirm 0 failures
- [ ] 3.3 Confirm `openspec validate --change trn-179-remove-ga-portal-enabled-branches` passes
