# testing/installation Specification

## Purpose

Defines verification coverage for installation behavior.

## Requirements

### Requirement: Static guardrail test prevents hardcoded pre-0.9.0 SEL path
The suite SHALL scan all `transport/` Python files and fail on pre-0.9.0 SEL path literals (`sel_key`, `sel-key`, `sel.key`, `/sel/`). It SHALL avoid false positives for SQL `SELECT`, `.local_secret`, and policy signing/trust keys.

#### Scenario: Test passes on clean tree
- **WHEN** the guardrail test is run against the transport source tree that contains no pre-0.9.0 SEL key path literal
- **THEN** the test passes with zero offenders reported

#### Scenario: Test fails when a pre-0.9.0 SEL literal is introduced
- **WHEN** any Python file under `transport/` is modified to include a string literal matching `sel_key`, `sel-key`, `sel.key`, or `/sel/` as a path segment
- **THEN** the guardrail test fails and identifies the offending file and line number

#### Scenario: SQL SELECT keyword is not a false positive
- **WHEN** the guardrail test runs and `transport/container_scripts/read_auth.py` contains `SELECT key, value FROM auth_kv`
- **THEN** the test passes; the SQL `SELECT` keyword does not match the SEL path pattern

#### Scenario: policy_signing_key and local_secret are not false positives
- **WHEN** the guardrail test runs and `transport/container_scripts/inject_policy.py` contains `policy_signing_key` and `trust_keys`, and `transport/lifecycle.py` contains `.local_secret`
- **THEN** the test passes; neither string matches the SEL path pattern

### Requirement: Installation and startup have an automated end-to-end smoke path
The supported release verification workflow SHALL include an automated install/start smoke path that exercises the generated service configuration, starts the transport and portal using Podman, verifies readiness through the published portal endpoint, and tears down the disposable test installation.

#### Scenario: Fresh disposable install reaches readiness
- **WHEN** the smoke workflow runs with a fresh temporary data directory and no existing Ghostship services
- **THEN** it generates configuration, starts the services, and receives a successful health response through the portal

#### Scenario: Failed readiness fails the smoke workflow
- **WHEN** the transport cannot become reachable through the portal within the configured readiness timeout
- **THEN** the smoke workflow fails and reports the portal-to-transport readiness failure

#### Scenario: Smoke workflow cleans up its disposable installation
- **WHEN** the readiness check succeeds or fails
- **THEN** the smoke workflow stops and removes only the services and temporary resources it created

### Requirement: Podman provisioning configuration has regression coverage
The installation test suite SHALL verify that Podman setup receives the effective dedicated-machine settings resolved from the selected YAML configuration.

#### Scenario: Repository configuration is used for provisioning
- **WHEN** installation tests provide repository YAML with non-default machine settings
- **THEN** the setup invocation uses the configured machine name and resource limits

#### Scenario: Explicit config precedence is preserved during provisioning
- **WHEN** repository, XDG, and explicit config files contain different machine settings
- **THEN** tests verify that provisioning uses only the explicit config layer over built-in defaults

#### Scenario: XDG config is used when repository config omits a machine setting
- **WHEN** repository YAML omits a machine setting and XDG YAML provides it
- **THEN** tests verify that the XDG value is used for Podman provisioning

#### Scenario: Ambient variables do not affect provisioning
- **WHEN** machine-related environment variables conflict with the selected YAML config
- **THEN** tests verify that the YAML values determine the Podman setup inputs

#### Scenario: Setup outputs match generated service configuration
- **WHEN** installation provisions a machine from resolved YAML values
- **THEN** tests verify the selected machine, socket, data directory, and generated Compose settings refer to the same instance
