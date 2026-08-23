## ADDED Requirements

### Requirement: Admiral secret delivered via environment, not on-disk policy file
The system SHALL NOT store the `admiral_secret` value in the plaintext `admission_policy.json` file seeded into the crew container. The admiral secret SHALL be delivered to the crew gateway via an environment variable (`KIRO_ADMIRAL_SECRET`) injected at container launch time, using the same Podman secret or env-var injection path used for other sensitive configuration. The policy file template SHALL omit the `admiral_secret` field; the gateway SHALL read it from the environment at startup.

#### Scenario: Crew container launched with admiral secret in environment
- **WHEN** a crew container is launched
- **THEN** the gateway process reads `KIRO_ADMIRAL_SECRET` from its environment and uses it to verify Admiral-signed messages

#### Scenario: admission_policy.json does not contain admiral_secret
- **WHEN** a crew's `admission_policy.json` is read by any process inside the crew container
- **THEN** the file does not contain the `admiral_secret` field, so an agent cannot extract it by reading that file

#### Scenario: Admiral message verification still works
- **WHEN** the Admiral sends a signed message to a crew that was launched with the new env-var delivery path
- **THEN** the crew gateway correctly verifies the signature using the secret received from the environment

#### Scenario: Missing admiral secret at startup is flagged
- **WHEN** a crew gateway starts and `KIRO_ADMIRAL_SECRET` is absent from the environment and absent from the policy file
- **THEN** the gateway logs a warning indicating that Admiral signature verification is disabled or unconfigured, rather than silently accepting all messages as valid

### Requirement: Threat model for admiral secret delivery is documented
The system's documentation SHALL describe the threat model for the admiral secret: why it must not reside in a file readable by agent processes, what privilege boundary the env-var delivery provides, and the residual risk (host-level access bypasses all container-side controls).

#### Scenario: Documentation covers admiral secret threat model
- **WHEN** a user or operator reads the security section of `docs/auth.md`
- **THEN** they find an explanation of why `admission_policy.json` no longer carries the secret, what the env-var boundary protects against, and what it does not protect against

### Requirement: Registry file written with restricted permissions
The system SHALL write `crews.json` with file permissions `0o600` (owner read/write only), ensuring the registry is not readable by other local users on the host.

#### Scenario: Registry written with 0o600 permissions
- **WHEN** `_save_registry` writes `crews.json`
- **THEN** the resulting file has permissions `0o600`

#### Scenario: Existing registry file permissions corrected on write
- **WHEN** `_save_registry` is called on a host where `crews.json` already exists with broader permissions
- **THEN** after the write the file has permissions `0o600`

### Requirement: dangerously_skip_permissions usage is annotated
Any call site in the codebase that passes `dangerously_skip_permissions=True` SHALL include an inline comment explaining why the permission bypass is required and what threat model constraint that implies.

#### Scenario: dangerously_skip_permissions call site has explanatory comment
- **WHEN** a developer reads the code at the `dangerously_skip_permissions=True` call site
- **THEN** the comment explains the purpose of the bypass and the security implication of enabling it
