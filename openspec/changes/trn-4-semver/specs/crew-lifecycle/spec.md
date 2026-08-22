## MODIFIED Requirements

### Requirement: Crew creation via launch
The system SHALL create an isolated crew container with a dedicated workspace volume and a dedicated home volume when `launch` is called with a valid, unique `crew_id`. The container image and manifest path SHALL be resolved from the crew-type registry based on the optional `composition` parameter (defaulting to `"kirocrew"`). At launch time, the system SHALL read the `org.ghostship.version` OCI label from the crew container and store it in the registry as `crew_image_version`.

#### Scenario: First launch for a new crew_id
- **WHEN** `launch` is called with a `crew_id` that has no existing registry entry and the registered crew count is below `GA_MAX_CREWS`
- **THEN** the system creates `gs-vol-<crew_id>` and `gs-home-<crew_id>` volumes, creates and starts a `gs-<crew_id>` container attached to `ga-net` using the image resolved from the crew type registry, reads the `org.ghostship.version` label from the container, stores it in the registry entry as `crew_image_version`, and waits up to 30 seconds for its gateway to respond on `:5476`

#### Scenario: Launch with composition parameter
- **WHEN** `launch` is called with a valid `crew_id` and `composition="worker"`
- **THEN** the system resolves the `"worker"` crew type's image and manifest from the registry and uses them instead of the hardcoded defaults

#### Scenario: Launch with unknown composition
- **WHEN** `launch` is called with a `composition` value not found in the loaded crew-type registry
- **THEN** the system returns an error listing the available crew types and creates no container

#### Scenario: Invalid crew_id
- **WHEN** `launch` is called with a `crew_id` that does not match lowercase alphanumeric/hyphen, 1-50 characters
- **THEN** the system returns an error and creates no container, volume, or registry entry

#### Scenario: Duplicate crew_id
- **WHEN** `launch` is called with a `crew_id` that already has a registry entry not in `auth_required` status
- **THEN** the system returns an error instructing the caller to nuke the existing crew first

#### Scenario: Max crews reached
- **WHEN** `launch` is called while the number of registered crews is already at or above `GA_MAX_CREWS`
- **THEN** the system returns an error and creates no container

#### Scenario: Gateway does not become ready
- **WHEN** the newly started crew container's gateway does not respond within 30 seconds
- **THEN** the system tears down the container and both volumes it just created and returns an error, leaving no partial registry entry

#### Scenario: Launch image without version label
- **WHEN** `launch` is called and the resolved container image does not carry the `org.ghostship.version` label
- **THEN** the system stores `"unknown"` as `crew_image_version` in the registry and proceeds normally — the missing label is not a launch failure

## ADDED Requirements

### Requirement: crews() includes crew image version
The `crews()` tool SHALL include a `crew_image_version` field in each crew entry, reflecting the version of the crew image that crew was built from. The value SHALL be sourced from the registry, populated at launch time.

#### Scenario: crews() shows version for a running crew
- **WHEN** `crews()` is called and a crew has `crew_image_version` stored in the registry
- **THEN** the crew entry includes `crew_image_version` with the stored semver string

#### Scenario: crews() for a crew launched before version tracking
- **WHEN** `crews()` is called and a crew's registry entry has no `crew_image_version` field
- **THEN** the crew entry includes `crew_image_version` set to `"unknown"`
