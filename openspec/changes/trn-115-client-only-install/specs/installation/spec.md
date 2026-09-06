## MODIFIED Requirements

### Requirement: Shell scripts reorganised under scripts/
`start.sh` and `uninstall.sh` SHALL be located at `scripts/start.sh` and `scripts/uninstall.sh` respectively. `install.sh` at the repo root SHALL remain as a shim that delegates to `scripts/install.sh` with all arguments forwarded, preserving backward compatibility for existing workflows. The shim SHALL forward `--client-only` and all other flags unchanged.

#### Scenario: start.sh and uninstall.sh in scripts/
- **WHEN** a user clones the repository
- **THEN** `scripts/start.sh` and `scripts/uninstall.sh` exist and are executable, and no `start.sh` or `uninstall.sh` exist at the repo root

#### Scenario: install.sh shim at root
- **WHEN** `./install.sh [flags]` is invoked
- **THEN** `scripts/install.sh [flags]` runs with all arguments forwarded and the exit code is preserved

#### Scenario: install.sh shim forwards --client-only
- **WHEN** `./install.sh --client-only [flags]` is invoked
- **THEN** `scripts/install.sh --client-only [flags]` runs with all arguments forwarded and the exit code is preserved
