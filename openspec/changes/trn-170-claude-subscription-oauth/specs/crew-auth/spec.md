## MODIFIED Requirements

### Requirement: Identity provider configuration

The system SHALL direct the device auth flow at a configured identity provider when `KIRO_IDENTITY_PROVIDER`/`KIRO_REGION`/`KIRO_LICENSE` are set, and SHALL fall back to Builder ID (free tier) when they are not. When falling back to Builder ID, `kiro-cli` may present an interactive login-method selection menu before the device code appears; the system SHALL answer that menu (accepting the Builder ID default) rather than treating its appearance as a failure.

When `KIRO_API_KEY` is set, the system SHALL skip the device-code auth flow entirely and inject the key as an env var into crew containers. The device-code path SHALL remain the default when `KIRO_API_KEY` is unset.

When `GA_CREW_ACP_BACKEND=claude` is set, the system SHALL skip all kiro-cli auth injection entirely (no device flow, no `ga-kiro-auth`, no `KIRO_API_KEY` injection). The system SHALL authenticate the Claude backend using one of two paths, checked in order:

1. **API key path**: If `GA_CREW_ANTHROPIC_API_KEY` is set, inject it as `ANTHROPIC_API_KEY` into the crew container environment.
2. **OAuth path**: If `ga-claude-auth` exists and is non-empty, inject the Claude OAuth credential into the crew container's `~/.claude/` directory.

If `GA_CREW_ACP_BACKEND=claude` and neither credential is available, `launch` SHALL return `not_authenticated` with a `login_url` pointing to the Claude device-code flow (initiated automatically), rather than a hard error.

#### Scenario: Claude backend — API key takes precedence over OAuth credential
- **WHEN** `GA_CREW_ACP_BACKEND=claude`, `GA_CREW_ANTHROPIC_API_KEY` is set, and `ga-claude-auth` also exists
- **THEN** `ANTHROPIC_API_KEY` is injected as an env var; the OAuth credential file is not injected; kiro auth is skipped entirely

#### Scenario: Claude backend — OAuth credential injected when no API key
- **WHEN** `GA_CREW_ACP_BACKEND=claude`, `GA_CREW_ANTHROPIC_API_KEY` is unset, and `ga-claude-auth` exists and is non-empty
- **THEN** the Claude credential from `ga-claude-auth` is injected into the crew container's `~/.claude/`; no `ANTHROPIC_API_KEY` env var is set; kiro auth is skipped

#### Scenario: Claude backend — neither credential present triggers OAuth login flow
- **WHEN** `GA_CREW_ACP_BACKEND=claude`, `GA_CREW_ANTHROPIC_API_KEY` is unset, and `ga-claude-auth` does not exist or is empty
- **THEN** `launch` returns `{"error": "not_authenticated", "login_url": "<url>", "code": "<code>", "instructions": "Open login_url to authenticate Claude, then call launch again."}` and does NOT create the crew container

#### Scenario: Claude backend — no kiro auth state required
- **WHEN** `GA_CREW_ACP_BACKEND=claude` and `ga-kiro-auth` does not exist
- **THEN** `launch` proceeds without requiring kiro auth state; absence of kiro-cli auth is not an error when the Claude backend is selected

#### Scenario: Identity provider configured (kiro path, unchanged)
- **WHEN** `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` are set on the transport container
- **THEN** the `kiro-cli login` command run during first-time auth includes `--identity-provider` and `--region` (and `--license` if `KIRO_LICENSE` is set)

#### Scenario: No identity provider configured (kiro path, unchanged)
- **WHEN** none of `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE` are set
- **THEN** `kiro-cli login` runs with only `--use-device-flow`, authenticating against the default Builder ID identity; if kiro-cli shows a login-method selection menu first, the system answers it to select Builder ID and the flow still completes with a device code and URL

#### Scenario: KIRO_API_KEY set — device flow skipped (unchanged)
- **WHEN** `KIRO_API_KEY` is set in the transport environment and `launch` is called
- **THEN** the system does NOT call `_initiate_login()`, does NOT require `ga-kiro-auth` to exist, and does NOT inject `auth_b64` rows into the crew's SQLite DB
- **THEN** `KIRO_API_KEY` is passed as an env var to the crew container at creation time

#### Scenario: KIRO_API_KEY unset — device flow unchanged
- **WHEN** `KIRO_API_KEY` is unset and `GA_CREW_ACP_BACKEND` is `kiro`
- **THEN** all existing device-code auth behaviour is unchanged — `ga-kiro-auth`, `_initiate_login()`, and `inject_auth.py` are used as before
