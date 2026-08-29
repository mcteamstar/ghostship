## MODIFIED Requirements

### Requirement: Transport service definition generated as a Compose file
`install.sh` SHALL copy the contents of `academy/` (subdirectories `agents`, `skills`, `steering`, `policies`, `orders`, `mcp`) and `crews/` from the ghostship repo into `${DATA_DIR}/academy/` and `${DATA_DIR}/crews/` respectively before writing `compose.yml`. These copies become the source of truth for the running transport container.

The seven volume entries in the generated `compose.yml` SHALL include `${DATA_DIR}/academy/mcp:/mcp:ro` alongside the existing academy and crews entries. The transport container's internal mount point for the catalogue SHALL be `/mcp`.

#### Scenario: install.sh copies academy/mcp into data volume
- **WHEN** `install.sh` completes the image build phase and `academy/mcp/` exists in the repo
- **THEN** `${DATA_DIR}/academy/mcp/` exists and contains the files from `academy/mcp/`

#### Scenario: install.sh generates compose.yml with /mcp mount
- **WHEN** `install.sh` completes the image build phase
- **THEN** `${DATA_DIR}/compose.yml` contains a volume entry `${DATA_DIR}/academy/mcp:/mcp:ro`
