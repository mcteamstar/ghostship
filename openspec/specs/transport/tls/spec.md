# transport/tls Specification

## Purpose

Auto-provisions TLS certificates via Caddy for every environment — local/private (internal CA), Tailscale (`.ts.net` trusted certs), public internet (ACME), and plain HTTP (off) — driven by a single mode variable.

## Requirements

### Requirement: Four-value TLS mode selection
`install.sh` SHALL read `GA_PORTAL_TLS_MODE` (values: `internal`, `tailscale`, `acme`, `off`; default: `internal`) and bake the appropriate TLS configuration into `initial-config.json`. TLS SHALL apply to every listener Caddy owns — the main port and every per-crew dashboard port. The transport SHALL NOT restart to activate or change TLS; TLS is owned entirely by Caddy.

#### Scenario: Internal CA mode (default)
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
When `GA_PORTAL_TLS_MODE=internal`, the install output SHALL print the path to Caddy's root CA certificate and instruct the operator to trust it once (e.g. `caddy trust` or importing it into the OS/browser trust store). `ghostship status` SHALL also surface this path. The install script SHALL NOT modify the system trust store automatically.

On macOS, the volume mountpoint returned by `podman volume inspect` is inside the Podman VM, so the certificate path printed by `ghostship status` and `install.sh` is not directly accessible on the host filesystem. When running on macOS, both outputs SHALL additionally print a `podman machine ssh` command that extracts the certificate from the VM and writes it to a host-accessible file, so the operator can import it into the macOS trust store without needing to know the VM path syntax.

#### Scenario: Install prints the CA path
- **WHEN** `install.sh` completes with `GA_PORTAL_TLS_MODE=internal`
- **THEN** the output includes the root CA certificate path and a trust instruction

#### Scenario: ghostship status reports the CA path
- **WHEN** `ghostship status` runs with `GA_PORTAL_TLS_MODE=internal`
- **THEN** its output includes the root CA certificate path

#### Scenario: macOS install prints host-extraction command
- **WHEN** `install.sh` completes with `GA_PORTAL_TLS_MODE=internal` on macOS
- **THEN** the output includes a `podman machine ssh <machine> cat <vm-cert-path>` command (or equivalent) that the operator can run on the host to extract the certificate

#### Scenario: macOS ghostship status prints host-extraction command
- **WHEN** `ghostship status` runs with `GA_PORTAL_TLS_MODE=internal` on macOS
- **THEN** its output includes a `podman machine ssh <machine> cat <vm-cert-path>` command (or equivalent) that the operator can run on the host to extract the certificate
