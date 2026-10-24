## ADDED Requirements

### Requirement: inject_auth.py uses stdin for kiro auth payload delivery

`inject_auth.py` SHALL read the base64-encoded kiro-cli auth row data from `sys.stdin`
(via `sys.stdin.read().strip()`), not from `sys.argv`. The caller in `lifecycle.py`
SHALL deliver the payload via the `stdin_data` parameter of `container_exec_stdin`,
closing the write end after the data is written. The `b64_rows` value SHALL NOT appear
in any element of `argv` of the `inject_auth.py` process.

#### Scenario: inject_auth.py auth payload not in argv

- **WHEN** `_inject_auth` is called to deliver kiro-cli auth rows into a crew container
- **THEN** the base64-encoded auth payload does not appear in any positional argument
  passed to the `inject_auth.py` process; it is delivered exclusively via stdin

#### Scenario: inject_auth.py auth payload delivered via stdin

- **WHEN** `_inject_auth` calls `container_exec_stdin` to run `inject_auth.py`
- **THEN** the base64-encoded auth rows are written to the process's stdin stream;
  the process reads them with `sys.stdin.read().strip()` and proceeds to insert rows

#### Scenario: inject_auth.py lifecycle caller uses container_exec_stdin

- **WHEN** `_inject_auth` is invoked with a non-empty `auth_b64` string
- **THEN** `container_exec_stdin` is called (not `container_exec_checked`), and the
  `auth_b64` value is passed as the `stdin_data` bytes argument
