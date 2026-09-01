## ADDED Requirements

### Requirement: Shell scripts reorganised under scripts/
`start.sh` and `uninstall.sh` SHALL be located at `scripts/start.sh` and `scripts/uninstall.sh` respectively. `install.sh` at the repo root SHALL remain as a shim that delegates to `scripts/install.sh` with all arguments forwarded, preserving backward compatibility for existing workflows.

#### Scenario: start.sh and uninstall.sh in scripts/
- **WHEN** a user clones the repository
- **THEN** `scripts/start.sh` and `scripts/uninstall.sh` exist and are executable, and no `start.sh` or `uninstall.sh` exist at the repo root

#### Scenario: install.sh shim at root
- **WHEN** `./install.sh [flags]` is invoked
- **THEN** `scripts/install.sh [flags]` runs with all arguments forwarded and the exit code is preserved

### Requirement: ghostship CLI available on PATH after install
`scripts/install.sh` SHALL make the `ghostship` CLI script available on `PATH` after a successful run.

#### Scenario: ~/.local/bin present and on PATH
- **WHEN** `scripts/install.sh` completes successfully and `~/.local/bin` exists and is on `PATH`
- **THEN** `~/.local/bin/ghostship` is a symlink pointing to the `ghostship` script in the repo

#### Scenario: ~/.local/bin not on PATH
- **WHEN** `scripts/install.sh` completes and `~/.local/bin` is not on `PATH`
- **THEN** `scripts/install.sh` prints a clear one-line message instructing the user to add `~/.local/bin` to their `PATH`
