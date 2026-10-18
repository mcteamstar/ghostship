## MODIFIED Requirements

### Requirement: Registry save is durable

The system SHALL write every secret or registry file through a single shared atomic-write utility (`_write_secret_file`) that opens the target `.tmp` path using `os.open` with mode `0o600`, calls `flush()` followed by `os.fsync()` on the file descriptor before closing, and fsyncs the containing directory — ensuring that on a crash or power loss after the write returns the data has been committed to stable storage. All credential and registry writers — the crew registry save, the admiral/crew secret writer, and each backend auth-file writer (kiro, claude, codex) — SHALL obtain their durability and permission guarantees from this one utility rather than each re-implementing the open/fsync sequence.

The `fd = -1` sentinel SHALL be assigned immediately after `os.fdopen()` succeeds and before the `with` body executes. This prevents a double-close on the underlying file descriptor if `os.fdopen()` itself raises (which would leave the `finally` block attempting to close an fd that `os.fdopen` has already taken ownership of). This invariant SHALL hold for every writer that routes through the shared utility.

The externally observable guarantees — mode `0o600` on the written file, data committed before the call returns, and no double-close on an `os.fdopen` failure — SHALL be identical before and after consolidation onto the shared utility. Consolidation is an internal change that MUST NOT alter the on-disk permission, durability, or atomicity behavior.

#### Scenario: Save survives process crash after write

- **WHEN** a registry or secret write through the shared utility returns successfully
- **THEN** the written data SHALL be present on disk even if the process is killed immediately after

#### Scenario: Temporary file has restricted permissions

- **WHEN** the shared utility creates the target `.tmp` file
- **THEN** the `.tmp` file SHALL have mode `0o600` (owner read/write only, no group or other access)

#### Scenario: fd sentinel set before with-body to prevent double-close

- **WHEN** the shared utility calls `os.fdopen(fd, ...)`
- **THEN** `fd` is immediately set to `-1` after `os.fdopen` returns, before any code in the `with` block executes
- **THEN** if any exception is raised inside the `with` block, the `finally` clause does not attempt to close the already-transferred fd

#### Scenario: All credential writers share one durable-write path

- **WHEN** any of the registry save, the crew/admiral secret write, or a kiro/claude/codex auth-file write is performed
- **THEN** each SHALL produce a file with mode `0o600`, fsynced before return, with no behavioral difference between writers in permission, durability, or atomicity
