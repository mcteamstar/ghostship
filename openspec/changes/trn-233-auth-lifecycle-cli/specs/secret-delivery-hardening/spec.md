# Spec Delta

## MODIFIED Requirements

### Requirement: Config repr masks sensitive credential fields
The `Config` dataclass SHALL hold no backend credential fields; backend credentials live only in the credential store. The credential store and its records SHALL override `__repr__` so that no credential value appears in `repr()` or `str()`. Any log call that includes `repr(cfg)`, `str(cfg)` or a credential record SHALL NOT emit live credential values.

#### Scenario: Config repr does not expose API keys
- **WHEN** `repr(cfg)` is called, or `repr()` is called on a stored credential record
- **THEN** the returned string contains no credential value; credential records show `***` in place of the value


## REMOVED Requirements

### Requirement: Model API keys are delivered as Podman secrets, not env vars
**Reason**: Backend API keys are now stored by the transport's credential store under `DATA_DIR` (mode `0600`) and supplied with `ghostship auth login <backend>`; they no longer pass through the installer, Podman secrets or the transport's environment.
**Migration**: None (breaking). After upgrading, re-enter credentials with `ghostship auth login <backend>`; old secrets are ignored.

### Requirement: KIRO_API_KEY is delivered as a Podman secret
**Reason**: The Kiro API key is one of the methods of `ghostship auth login kiro` and stored by the credential store.
**Migration**: None (breaking). After upgrading, re-enter credentials with `ghostship auth login <backend>`; old secrets are ignored.

### Requirement: Claude OAuth token is delivered as a Podman secret
**Reason**: The setup-token is one of the methods of `ghostship auth login claude` and stored by the credential store.
**Migration**: None (breaking). After upgrading, re-enter credentials with `ghostship auth login <backend>`; old secrets are ignored.
