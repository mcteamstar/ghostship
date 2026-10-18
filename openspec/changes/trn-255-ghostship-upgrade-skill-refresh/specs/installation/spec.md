# Spec Delta

## MODIFIED Requirements

### Requirement: Wizard generates ghostship.yaml
The install wizard (run on first install or with `--wizard`) SHALL generate
`config/ghostship.yaml` with operator-supplied values and inline comments from an
internal template. It SHALL NOT generate `ghostship.conf`.

After the transport has passed its health check, the wizard SHALL unconditionally run `ghostship setup` to wire skill symlinks and register the MCP server for all detected agent clients. No confirmation prompt is shown for this step — the wizard always wires harnesses on a successful first install.

#### Scenario: Wizard writes YAML config
- **WHEN** the wizard completes
- **THEN** `config/ghostship.yaml` exists with the operator's choices and all other keys commented out at their defaults

#### Scenario: Wizard does not overwrite existing config
- **WHEN** `config/ghostship.yaml` already exists and `--wizard` is passed
- **THEN** the wizard prompts before overwriting (existing behaviour preserved)

#### Scenario: Wizard runs ghostship setup unconditionally
- **WHEN** the wizard completes and the transport passes its health check
- **THEN** `ghostship setup` is invoked automatically with no confirmation prompt, and skill symlinks and MCP registration are applied for all detected agent clients

#### Scenario: Wizard setup fails gracefully
- **WHEN** `ghostship setup` invoked by the wizard exits non-zero (e.g. no supported agent client detected)
- **THEN** a warning is printed but the overall install exits 0; `ghostship setup` can be re-run manually
