## MODIFIED Requirements

### Requirement: Path canonicalisation
All user-supplied paths MUST be resolved with `Path.resolve()` relative to the crew workspace
root before use. Any path that resolves outside the workspace root MUST be rejected with a 400
error. Checking for `..` components alone is not sufficient. The prefix check MUST append `/`
to the root string (i.e. `startswith(str(root) + "/")`) to prevent adjacent-directory bypass
where a path such as `/workspace-evil/secret` would incorrectly pass a check against root `/workspace`.

#### Scenario: Path traversal via dot-dot is rejected
- **WHEN** a caller supplies a path such as `../../etc/passwd`
- **THEN** the transport returns a 400 error and does not access the file

#### Scenario: Path traversal without dot-dot is rejected
- **WHEN** a caller supplies a path such as `repo/./../../etc/shadow` that resolves outside the workspace
- **THEN** the transport returns a 400 error

#### Scenario: Adjacent-directory path is rejected
- **WHEN** a caller supplies a path that resolves to a directory whose name starts with the workspace root name but is outside it (e.g. root is `/workspace`, path resolves to `/workspace-evil/secret`)
- **THEN** the transport returns a 400 error

#### Scenario: Valid workspace path is accepted
- **WHEN** a caller supplies a path such as `repo/src/main.py` that resolves inside the workspace
- **THEN** the request proceeds normally
