# registry/durability Specification

## Purpose

Defines the durability and integrity guarantees for the crew registry file: atomic writes with kernel-level flush, restricted permissions on intermediate files, and loud failure on corrupt data rather than silent empty-state masking.
## Requirements
### Requirement: Registry file written with restricted permissions
The system SHALL write `crews.json` with file permissions `0o600` (owner read/write only), ensuring the registry is not readable by other local users on the host.

#### Scenario: Registry written with 0o600 permissions
- **WHEN** `_save_registry` writes `crews.json`
- **THEN** the resulting file has permissions `0o600`

#### Scenario: Existing registry file permissions corrected on write
- **WHEN** `_save_registry` is called on a host where `crews.json` already exists with broader permissions
- **THEN** after the write the file has permissions `0o600`

### Requirement: Registry writes use one durable atomic path

Credential and registry files SHALL use `_write_secret_file`: open `.tmp` with mode `0o600`, flush and fsync the file, then fsync its directory before return. Consolidation SHALL preserve each writer's permissions, durability, and atomicity.

#### Scenario: Save survives process crash after write

- **WHEN** a registry or secret write through the shared utility returns successfully
- **THEN** the written data SHALL be present on disk even if the process is killed immediately after

#### Scenario: Temporary file has restricted permissions

- **WHEN** the shared utility creates the target `.tmp` file
- **THEN** the `.tmp` file SHALL have mode `0o600` (owner read/write only, no group or other access)

#### Scenario: All credential writers share one durable-write path

- **WHEN** any of the registry save, the crew/admiral secret write, or a kiro/claude/codex auth-file write is performed
- **THEN** each SHALL produce a file with mode `0o600`, fsynced before return, with no behavioral difference between writers in permission, durability, or atomicity

### Requirement: Atomic writer transfers descriptor ownership safely

The writer SHALL set `fd = -1` immediately after `os.fdopen()` succeeds and before the `with` body, preventing a double-close if `fdopen` raises.

#### Scenario: fd sentinel set before with-body to prevent double-close

- **WHEN** the shared utility calls `os.fdopen(fd, ...)`
- **THEN** `fd` is immediately set to `-1` after `os.fdopen` returns, before any code in the `with` block executes
- **THEN** if any exception is raised inside the `with` block, the `finally` clause does not attempt to close the already-transferred fd

### Requirement: Registry load fails loudly on corrupt data

The system SHALL raise an exception when `_load_registry` encounters a file that exists but contains invalid JSON. It SHALL NOT silently return an empty dict in that case.

#### Scenario: Corrupt JSON raises and quarantines the file

- **WHEN** `crews.json` exists and contains invalid JSON
- **THEN** `_load_registry` SHALL log at `ERROR` level, rename the file to `crews.json.corrupt`, and raise an exception

#### Scenario: Corrupt file is renamed before raise

- **WHEN** `crews.json` contains invalid JSON and `_load_registry` is called
- **THEN** the original file SHALL be renamed to `crews.json.corrupt` before the exception propagates, so the corrupt data is preserved for inspection and does not block re-creation of a fresh registry

#### Scenario: Missing file still returns empty registry

- **WHEN** `crews.json` does not exist
- **THEN** `_load_registry` SHALL return `{"crews": {}}` without error (no change to existing behavior)
