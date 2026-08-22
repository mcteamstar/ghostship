## MODIFIED Requirements

### Requirement: GA_API_KEY is delivered to the transport container via Podman secret
The installation SHALL create a Podman secret named `ga-api-key` (via `podman secret create`) containing the operator-supplied API key. The transport container SHALL receive the secret via `--secret ga-api-key` and read it from `/run/secrets/ga-api-key` at startup. The `-e GA_API_KEY=...` environment variable SHALL NOT be passed to the container.

When `--api-key` is not provided and no persisted key file exists, the secret SHALL NOT be created and the container SHALL start without `--secret ga-api-key` (authentication disabled).

#### Scenario: Fresh install with --api-key flag
- **WHEN** `install.sh` is run with `--api-key <value>`
- **THEN** `podman secret create ga-api-key` is invoked with the provided value, the transport container is started with `--secret ga-api-key`, and `/run/secrets/ga-api-key` inside the container contains the key

#### Scenario: Re-install with persisted key
- **WHEN** `install.sh` is run without `--api-key` but a persisted key file exists in DATA_DIR
- **THEN** the existing `ga-api-key` Podman secret is removed and recreated from the persisted file, and the container uses the refreshed secret

#### Scenario: Install without API key
- **WHEN** `install.sh` is run without `--api-key` and no persisted key file exists
- **THEN** no Podman secret is created, the container starts without `--secret`, and MCP API-key authentication is disabled

#### Scenario: API key not visible via podman inspect or /proc
- **WHEN** the transport container is running with `--secret ga-api-key`
- **THEN** `podman inspect ga-transport` does not show the API key in `Config.Env` or any other field, and `/proc/1/environ` inside the container does not contain `GA_API_KEY`

### Requirement: Transport reads GA_API_KEY from the secrets filesystem
The transport server process SHALL read the API key from `/run/secrets/ga-api-key` at startup. If the file does not exist or is empty, the transport SHALL behave as if no API key was configured (authentication disabled). The `GA_API_KEY` environment variable SHALL be treated as a deprecated fallback: if the file is absent but the env var is set, the transport SHALL use the env var and log a deprecation warning.

#### Scenario: Secret file present
- **WHEN** the transport starts and `/run/secrets/ga-api-key` exists with non-empty content
- **THEN** the transport uses its content (stripped of leading/trailing whitespace) as the bearer token for authentication

#### Scenario: Secret file absent, env var set (deprecated fallback)
- **WHEN** the transport starts and `/run/secrets/ga-api-key` does not exist but `GA_API_KEY` env var is set
- **THEN** the transport uses the env var value and logs a deprecation warning at startup

#### Scenario: Neither secret file nor env var
- **WHEN** the transport starts and neither `/run/secrets/ga-api-key` nor `GA_API_KEY` env var is available
- **THEN** API-key authentication is disabled and the transport logs an info message
