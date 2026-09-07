# registry/durability Specification

## Purpose

Defines the durability and integrity guarantees for the crew registry file: atomic writes with kernel-level flush, restricted permissions on intermediate files, and loud failure on corrupt data rather than silent empty-state masking.
## Requirements
### Requirement: Registry save is durable

The system SHALL write the registry `.tmp` file using `os.open` with mode `0o600` and SHALL call `flush()` followed by `os.fsync()` on the file descriptor before closing, ensuring that on a crash or power loss after `_save_registry` returns the data has been committed to stable storage.

The `fd = -1` sentinel SHALL be assigned immediately after `os.fdopen()` succeeds and before the `with` body executes. This prevents a double-close on the underlying file descriptor if `os.fdopen()` itself raises (which would leave the `finally` block attempting to close an fd that `os.fdopen` has already taken ownership of). The same invariant SHALL apply to `_write_auth_file()` in `transport/server.py`.

#### Scenario: Save survives process crash after write

- **WHEN** `_save_registry` returns successfully
- **THEN** the registry data SHALL be present on disk even if the process is killed immediately after

#### Scenario: Temporary file has restricted permissions

- **WHEN** `_save_registry` creates the `.tmp` file
- **THEN** the `.tmp` file SHALL have mode `0o600` (owner read/write only, no group or other access)

#### Scenario: fd sentinel set before with-body to prevent double-close

- **WHEN** `_save_registry` or `_write_auth_file` calls `os.fdopen(fd, ...)`
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

