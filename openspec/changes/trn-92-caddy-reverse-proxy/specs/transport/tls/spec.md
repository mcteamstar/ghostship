## Purpose

Auto-provisions TLS certificates via Caddy for all three target environments — local dev (internal CA), remote/Tailscale (ACME), and explicit cert (bring-your-own) — replacing the manual `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` path with a mode-driven configuration.

## ADDED Requirements

### Requirement: TLS mode selection
When `GA_CADDY_ENABLED=true`, `install.sh` SHALL read `GA_CADDY_TLS_MODE` (values: `internal`, `acme`, `off`; default: `internal`) and bake the appropriate TLS stanza into `initial-config.json`. The transport SHALL NOT need to restart to activate TLS; TLS is entirely owned by Caddy.

#### Scenario: Internal CA mode for local installs
- **WHEN** `GA_CADDY_TLS_MODE=internal`
- **THEN** `initial-config.json` includes a `tls: { "automation": { "policies": [{ "subjects": ["<domain>"], "issuers": [{ "module": "internal" }] }] } }` block
- **THEN** Caddy generates a locally-trusted certificate using its built-in CA

#### Scenario: ACME mode for remote installs
- **WHEN** `GA_CADDY_TLS_MODE=acme` and `GA_CADDY_DOMAIN` is set
- **THEN** `initial-config.json` includes a standard ACME issuer stanza
- **THEN** Caddy provisions and auto-renews a Let's Encrypt or ZeroSSL certificate for `GA_CADDY_DOMAIN`

#### Scenario: TLS off (plain HTTP through Caddy)
- **WHEN** `GA_CADDY_TLS_MODE=off`
- **THEN** Caddy serves HTTP only on port 80
- **THEN** no certificate provisioning occurs

### Requirement: Internal CA certificate trust
When `GA_CADDY_TLS_MODE=internal`, `install.sh` SHALL print instructions for adding the Caddy local CA root to the host's trust store using `caddy trust` (or equivalent). The install script SHALL NOT modify the system trust store automatically.

#### Scenario: Install script prints trust instructions
- **WHEN** `install.sh` completes with `GA_CADDY_TLS_MODE=internal`
- **THEN** the output includes a line instructing the user to run `caddy trust` or equivalent to add the local CA

### Requirement: Direct TLS fallback unaffected
When `GA_CADDY_ENABLED=false`, the existing `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` direct TLS termination path in the transport SHALL remain functional and SHALL NOT be deprecated by this change.

#### Scenario: Direct TLS still works without Caddy
- **WHEN** `GA_CADDY_ENABLED=false` and `GA_TLS_CERTFILE`/`GA_TLS_KEYFILE` are set
- **THEN** the transport serves HTTPS directly as before
