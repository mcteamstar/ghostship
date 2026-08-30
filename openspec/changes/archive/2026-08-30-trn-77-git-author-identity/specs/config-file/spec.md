## MODIFIED Requirements

### Requirement: Config file with all supported variables
The system SHALL accept a `--config <path>` flag pointing to a shell file that exports configuration variables. When a config file exports any combination of: `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE`, `PORT`, `KC_MODEL_OVERRIDE`, `KC_MODEL_DEFAULT`, `GA_API_KEY`, `GA_HOST_URL`, `GA_DEDICATED_MACHINE`, `GA_MACHINE_NAME`, `GA_MACHINE_CPUS`, `GA_MACHINE_MEMORY`, `GA_MACHINE_DISK`, `GA_GIT_AUTHOR_NAME`, `GA_GIT_AUTHOR_EMAIL`, each exported variable SHALL act as a default, overridable by its corresponding flag where one exists.

#### Scenario: Config file sets git author identity
- **WHEN** `install.sh` runs with `--config ./my.conf` and `my.conf` exports `GA_GIT_AUTHOR_NAME="Your Name"` and `GA_GIT_AUTHOR_EMAIL="you@example.com"`
- **THEN** crew containers SHALL have `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and `GIT_COMMITTER_EMAIL` set to the configured values

#### Scenario: Git identity vars absent — per-persona identity preserved
- **WHEN** `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are not set
- **THEN** crew containers SHALL use the per-persona git identity (e.g. `Ghost <ghost@localhost>`) as before — no breaking change

## ADDED Requirements

### Requirement: Operator-configurable git author identity for crew commits
The system SHALL optionally inject `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and `GIT_COMMITTER_EMAIL` environment variables into crew containers at creation time when `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are set. When set, all commits made by agents inside the crew SHALL carry the operator's configured identity as both author and committer.

#### Scenario: Git identity injected when configured
- **WHEN** `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are set and a crew is launched
- **THEN** the crew container has all four git identity env vars set to the configured values

#### Scenario: Identity not injected when unconfigured
- **WHEN** `GA_GIT_AUTHOR_NAME` is unset
- **THEN** the crew container does not have `GIT_AUTHOR_NAME` or `GIT_COMMITTER_NAME` in its environment — kiro-cli uses its own per-session identity
