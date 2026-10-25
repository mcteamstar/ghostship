## MODIFIED Requirements

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
