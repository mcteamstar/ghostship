# Spec Delta

## Purpose

Defines and enforces the project's policy for `except Exception:` usage in the transport layer and the `ghostship` CLI — specifying when broad catching is permitted and what annotation is required when it is.

## ADDED Requirements

### Requirement: Broad except clauses in critical paths MUST be replaced or annotated

In `transport/captain.py`, `transport/lifecycle.py`, and the `ghostship` CLI script, any `except Exception:` clause that discards all errors in a code path that affects correctness (recovery probes, session cookie operations, schedule reads) SHALL either be replaced with a specific exception type list, or carry an inline comment of the form `# best-effort: <reason>` explaining why broad catching is intentional.

#### Scenario: Recovery probe uses specific exception types

- **WHEN** the liveness probe in `_probe_gateway` encounters a connection error
- **THEN** only `(httpx.ConnectError, httpx.ConnectTimeout, ConnectionError, OSError)` are caught and return `False`, not every possible exception

#### Scenario: Best-effort fallback retains broad catch with rationale comment

- **WHEN** a non-critical helper (sentinel file read, mail subject scan) uses `except Exception:`
- **THEN** the clause is immediately preceded by a comment of the form `# best-effort: <reason>` so reviewers can distinguish intentional from accidental broad catching

#### Scenario: Security-sensitive path uses specific exception types

- **WHEN** `verify_password()` or any path involved in auth decision-making catches exceptions
- **THEN** only the documented exception types specific to the hash library are caught; bare `except Exception:` is absent from those paths

### Requirement: CLI helpers use specific exception types for subprocess and IO errors

The `ghostship` CLI script's subprocess-wrapping helpers (`cmd_status`, `_inspect_installed_url`, `_inspect_installed_api_key`, `_portal_data_mountpoint`) SHALL catch `(subprocess.CalledProcessError, FileNotFoundError, PermissionError, json.JSONDecodeError, OSError)` instead of bare `except Exception:`.

#### Scenario: Status command survives a missing container gracefully

- **WHEN** the `ga-transport` container is absent and `ghostship status` is run
- **THEN** the command prints a clear message and exits non-zero without an unhandled traceback

#### Scenario: Inspect helper returns empty string on unexpected subprocess failure

- **WHEN** `_inspect_installed_url` encounters an unexpected subprocess error
- **THEN** it returns an empty string (same as before), but the exception is logged at DEBUG rather than silently swallowed

