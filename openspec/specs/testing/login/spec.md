# testing/login Specification

## Purpose

Defines verification coverage for backend login, credential capture and login concurrency.

## Requirements

### Requirement: Login flow edge case tests

The test suite SHALL exercise untested paths in the PTY-based login flow.

#### Scenario: URL not found within timeout
- **WHEN** `_handle_login_post` starts a PTY exec AND no device URL appears within 15 seconds
- **THEN** the login container is cleaned up and a 500 response is returned

#### Scenario: Region prompt answered
- **WHEN** `_handle_login_post` encounters a "Region" prompt in PTY output after answering the Start URL prompt
- **THEN** the configured `KIRO_REGION` value is written to the PTY stdin

#### Scenario: Concurrent POST /login rejection
- **WHEN** a `POST /login` arrives while `_login_pending` is not None
- **THEN** a 409 response is returned with message "Login already in progress"

#### Scenario: _handle_login_get clears pending guard on completion
- **WHEN** `_handle_login_get` detects auth completion
- **THEN** `_login_pending` is set to None under the lock AFTER the login container is nuked

### Requirement: _handle_login_get clears guard correctly under concurrency

The `_handle_login_get` handler SHALL clear `_login_pending` only after all
cleanup work (auth write, crew injection, container nuke) is complete, to
prevent a concurrent `POST /login` from starting a new flow while cleanup
artifacts (the login container) still exist.

#### Scenario: Guard cleared after container nuke
- **WHEN** `_handle_login_get` completes the auth flow
- **THEN** `_login_pending` is set to None strictly AFTER `_nuke_login_container` returns

#### Scenario: Concurrent POST during cleanup window
- **WHEN** a `POST /login` arrives while `_handle_login_get` is between auth detection and guard clear
- **THEN** the POST receives 409 (the guard is still set)

### Requirement: Claude login lifecycle test coverage
The test suite SHALL exercise the Claude OAuth login flow: `_start_claude_login_container` (container start, binary probe), `_initiate_claude_login` (PTY exec, URL extraction, timeout), and `_nuke_claude_login_container` (container cleanup). Tests SHALL mirror the structure of the existing Codex login tests (`test_trn172_codex_backend.py`). `container_exec_stdin` SHALL be mocked for PTY interaction.

#### Scenario: Claude login extracts URL from PTY output
- **WHEN** `_initiate_claude_login` runs and the PTY emits a login URL
- **THEN** the URL is extracted and returned as the login URL

#### Scenario: Claude login times out if no URL appears
- **WHEN** `_initiate_claude_login` runs and no URL appears within the timeout
- **THEN** the login container is nuked and a timeout error is returned
