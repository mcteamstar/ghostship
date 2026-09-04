## MODIFIED Requirements

### Requirement: Identity provider configuration

The system SHALL direct the device auth flow at a configured identity provider when `KIRO_IDENTITY_PROVIDER`/`KIRO_REGION`/`KIRO_LICENSE` are set, and SHALL fall back to Builder ID (free tier) when they are not. When falling back to Builder ID, `kiro-cli` may present an interactive login-method selection menu before the device code appears; the system SHALL answer that menu (accepting the Builder ID default) rather than treating its appearance as a failure.

When `KIRO_API_KEY` is set, the system SHALL skip the device-code auth flow entirely and inject the key as an env var into crew containers. The device-code path SHALL remain the default when `KIRO_API_KEY` is unset.

#### Scenario: Identity provider configured

- **WHEN** `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` are set on the transport container
- **THEN** the `kiro-cli login` command run during first-time auth includes `--identity-provider` and `--region` (and `--license` if `KIRO_LICENSE` is set)

#### Scenario: No identity provider configured

- **WHEN** none of `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE` are set
- **THEN** `kiro-cli login` runs with only `--use-device-flow`, authenticating against the default Builder ID identity; if kiro-cli shows a login-method selection menu first, the system answers it to select Builder ID and the flow still completes with a device code and URL

#### Scenario: KIRO_API_KEY set — device flow skipped

- **WHEN** `KIRO_API_KEY` is set in the transport environment and `launch` is called
- **THEN** the system does NOT call `_initiate_login()`, does NOT require `ga-kiro-auth` to exist, and does NOT inject `auth_b64` rows into the crew's SQLite DB
- **THEN** `KIRO_API_KEY` is passed as an env var to the crew container at creation time
- **THEN** kiro-cli inside the crew authenticates via the env var without a device-code exchange

#### Scenario: KIRO_API_KEY unset — device flow unchanged

- **WHEN** `KIRO_API_KEY` is unset
- **THEN** all existing device-code auth behaviour is unchanged — `ga-kiro-auth`, `_initiate_login()`, and `inject_auth.py` are used as before
