## MODIFIED Requirements

### Requirement: Missing or malformed manifest defaults to "*"
The system SHALL treat a missing manifest file, a missing key within an existing manifest, or a manifest that fails to parse as JSON, as equivalent to `"*"` for the affected section(s). The system SHALL log a warning when this happens and SHALL NOT fail crew setup because of it. Additionally, at transport startup the system SHALL validate all manifests present in the loaded crew-type registry and log a startup warning for any manifest that references an agent, skill, or steering name that does not exist in the corresponding Academy pool; the warning SHALL identify the crew type, the missing name, and the pool it was expected to be in.

#### Scenario: No manifest file present
- **WHEN** a crew type's resolved manifest path does not point to an existing file
- **THEN** `launch` proceeds by copying every agent, skill, and steering file in the respective Academy pools, exactly as if the manifest specified `"*"` for each, and a warning is logged

#### Scenario: Manifest is present but malformed
- **WHEN** a crew type's `manifest.json` exists but is not valid JSON
- **THEN** `launch` proceeds as if the manifest specified `"*"` for every section, and a warning is logged, rather than failing crew setup

#### Scenario: Startup validation warns on unknown agent name
- **WHEN** the transport starts and a manifest lists an agent name that has no corresponding `.json` file in the Academy agents pool
- **THEN** a startup warning is logged identifying the crew type and the unknown name; crew setup for that crew type is not prevented

#### Scenario: Startup validation passes for valid manifests
- **WHEN** the transport starts and all manifests reference only names that exist in their respective Academy pools
- **THEN** no validation warning is logged for manifests
