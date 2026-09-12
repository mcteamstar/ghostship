# trn-cli — Delta Spec (trn-150-ghostship-auth-cli)

Updates to the `trn-cli` capability.

## ADDED Requirements

### Requirement: Auth subcommand group

The system SHALL provide a `ghostship auth` subcommand group that exposes device auth operations directly from the CLI. Running `ghostship auth` with no sub-subcommand SHALL print usage help for the group and exit 0.

Both `auth login` and `auth logout` SHALL accept:
- `--url <transport-url>` — override the transport base URL (default: `GHOSTSHIP_URL` env var, then `http://localhost:64057`)
- `--api-key <key>` — Bearer token for transports that require auth

#### Scenario: ghostship auth — no sub-subcommand
- **WHEN** `ghostship auth` is invoked with no sub-subcommand
- **THEN** usage help for the `auth` group is printed and the process exits 0

#### Scenario: ghostship auth login — success
- **WHEN** `ghostship auth login` is invoked and the transport returns a device code response
- **THEN** the activation URL and user code are printed clearly, the CLI polls until auth completes, and "Authenticated successfully." is printed before exit 0

#### Scenario: ghostship auth login — already authenticated
- **WHEN** `ghostship auth login` is invoked and the transport reports auth is already present
- **THEN** a message such as "Already authenticated." is printed and the process exits 0

#### Scenario: ghostship auth login — timeout
- **WHEN** `ghostship auth login` is invoked but the user does not complete the flow within the polling window (default ~5 min)
- **THEN** a timeout message is printed that includes the activation URL again, and the process exits non-zero

#### Scenario: ghostship auth login — transport unreachable
- **WHEN** `ghostship auth login` is invoked and the transport URL is not reachable
- **THEN** a clear error message is printed (including the URL tried) and the process exits non-zero

#### Scenario: ghostship auth logout — success
- **WHEN** `ghostship auth logout` is invoked
- **THEN** `POST /logout` is called, "Logged out." is printed, and the process exits 0

#### Scenario: ghostship auth logout — transport unreachable
- **WHEN** `ghostship auth logout` is invoked and the transport URL is not reachable
- **THEN** a clear error message is printed and the process exits non-zero

#### Scenario: ghostship auth login — custom URL
- **WHEN** `ghostship auth login --url https://remote.example.com` is invoked
- **THEN** the auth flow targets that URL instead of the default

#### Scenario: ghostship auth login — GHOSTSHIP_URL env var
- **WHEN** `GHOSTSHIP_URL=http://my-host:64057` is set and `ghostship auth login` is invoked without `--url`
- **THEN** the auth flow targets `http://my-host:64057`
