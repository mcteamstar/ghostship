# transport/tls Specification

## Purpose

Auto-provisions TLS certificates via Caddy for local/private (internal CA), Tailscale (`.ts.net` trusted certs), public internet (ACME), and plain HTTP (off). The default mode is plain HTTP.

## Requirements

### Requirement: Four-value TLS mode selection
`install.sh` SHALL read `GA_PORTAL_TLS_MODE` (values: `internal`, `tailscale`, `acme`, `off`; default: `off`) and bake the appropriate TLS configuration into `initial-config.json`. TLS SHALL apply to every listener Caddy owns — the main port and every per-crew dashboard port. The transport SHALL NOT restart to activate or change TLS; TLS is owned entirely by Caddy.

#### Scenario: Internal CA mode
- **WHEN** `GA_PORTAL_TLS_MODE=internal`
- **THEN** Caddy issues self-signed certificates from its built-in local CA for all listeners
- **THEN** certificates are valid on localhost, private IPs, Tailscale addresses, and any hostname

#### Scenario: Tailscale mode
- **WHEN** `GA_PORTAL_TLS_MODE=tailscale` and the Tailscale daemon is present on the host
- **THEN** Caddy provisions browser-trusted certificates for the `.ts.net` hostname via Tailscale's ACME endpoint
- **THEN** no manual certificate-trust step is required

#### Scenario: Public ACME mode
- **WHEN** `GA_PORTAL_TLS_MODE=acme` and `GA_PORTAL_DOMAIN` is set and ports 80/443 are reachable
- **THEN** Caddy provisions and auto-renews a public (Let's Encrypt) certificate for `GA_PORTAL_DOMAIN`

#### Scenario: TLS off
- **WHEN** `GA_PORTAL_TLS_MODE=off`
- **THEN** Caddy serves plain HTTP only and no certificate provisioning occurs

### Requirement: Internal CA root certificate path is surfaced

In internal TLS mode, install output and `ghostship status` SHALL print Caddy's root CA path and instruct one-time trust; the installer SHALL NOT modify the system trust store.

#### Scenario: Install prints the CA path
- **WHEN** `install.sh` completes with `GA_PORTAL_TLS_MODE=internal`
- **THEN** the output includes the root CA certificate path and a trust instruction

#### Scenario: ghostship status reports the CA path
- **WHEN** `ghostship status` runs with `GA_PORTAL_TLS_MODE=internal`
- **THEN** its output includes the root CA certificate path

### Requirement: macOS outputs include a host-accessible CA extraction command

On macOS, install and status SHALL also print a `podman machine ssh` command that copies the CA from the VM to a host-accessible file.

#### Scenario: macOS install prints host-extraction command
- **WHEN** `install.sh` completes with `GA_PORTAL_TLS_MODE=internal` on macOS
- **THEN** the output includes a `podman machine ssh <machine> cat <vm-cert-path>` command (or equivalent) that the operator can run on the host to extract the certificate

#### Scenario: macOS ghostship status prints host-extraction command
- **WHEN** `ghostship status` runs with `GA_PORTAL_TLS_MODE=internal` on macOS
- **THEN** its output includes a `podman machine ssh <machine> cat <vm-cert-path>` command (or equivalent) that the operator can run on the host to extract the certificate
