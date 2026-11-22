## ADDED Requirements

### Requirement: Upload mutations stay within the crew workspace

Plain uploads, archive unpack, bundle clone, and forced replacement SHALL confine destination mutations to the target crew workspace.

#### Scenario: Upload targets a valid nested workspace path

- **WHEN** a signed upload targets a valid nested destination in the crew workspace
- **THEN** the supported upload operation succeeds as before

#### Scenario: Destination cannot be confined

- **WHEN** the destination or an archive member cannot be safely confined to the workspace
- **THEN** the upload is rejected before destination mutation
- **AND** existing destination data is preserved and staging files are removed
