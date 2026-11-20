# Spec Delta

## ADDED Requirements

### Requirement: Python integration suites run through the supported test workflow
The supported test workflow SHALL execute the repository's Python integration suites, including profile launch flow, on-demand recovery, model defaults, and Codex sandbox coverage. Tests requiring a built crew image or Podman connection MAY run in a dedicated Podman-backed CI job, but SHALL be included in the documented release verification workflow and SHALL report failures as CI failures.

#### Scenario: Lightweight Python integration tests run in CI
- **WHEN** CI runs the integration test category
- **THEN** the profile launch-flow and on-demand recovery Python suites run with their declared Python dependencies

#### Scenario: Crew-image integration tests run in Podman-backed CI
- **WHEN** CI runs the Podman-backed integration category
- **THEN** it builds or selects the required crew image and runs the model-default and Codex-sandbox suites against a disposable container
- **THEN** failures in those suites fail the CI job

### Requirement: Admiral signature verifier has direct behavioral coverage
The test suite SHALL execute `verify-admiral-sig` against a valid signed message, a modified or invalidly signed message, and a message whose public key is missing. The tests SHALL verify the documented exit-code contract: 0 for a valid signature, 1 for invalid or malformed mail, and 2 when verification cannot proceed because the public key is absent.

#### Scenario: Valid signed message is accepted
- **WHEN** the verifier receives a message signed by the private key matching the mounted test public key
- **THEN** it exits with code 0

#### Scenario: Tampered message is rejected
- **WHEN** the verifier receives a message whose signed subject or body has been changed
- **THEN** it exits with code 1

#### Scenario: Malformed signature is rejected
- **WHEN** the verifier receives a malformed signature or malformed signed-message structure
- **THEN** it exits with code 1 and reports the message as invalid

#### Scenario: Missing public key is reported as unverifiable
- **WHEN** the verifier cannot read the public key after its retry window
- **THEN** it exits with code 2

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
