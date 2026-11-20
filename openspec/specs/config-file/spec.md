# Config File Specification

## Purpose

Allow operators to set install.sh defaults in a YAML config file rather than passing long flag lists on every invocation. The config file is merged on top of built-in defaults before flag parsing so command-line flags always override config-file values.

## Requirements

### Requirement: Config file sourcing follows explicit precedence

The system SHALL resolve `--config` values from built-in defaults then that file, replacing repo and XDG layers; without it, values resolve from built-in defaults, repo config, then XDG override. CLI flags take precedence, and ambient shell variables are not configuration inputs.

#### Scenario: Config file sets defaults, no flags override
- **WHEN** `install.sh` runs with `--config ./my.yaml` and `my.yaml` sets `network.port: 9000`
- **AND** no `--port` flag is passed
- **THEN** the transport SHALL use port `9000`

#### Scenario: Command-line flag overrides config file
- **WHEN** `install.sh` runs with `--config ./my.yaml --port 8000` and `my.yaml` sets `network.port: 9000`
- **THEN** the transport SHALL use port `8000` (flag wins)

#### Scenario: Config file sets identity provider
- **WHEN** install.sh runs with `--config ./my.yaml` and `my.yaml` sets `backends.kiro.identity_provider` and `backends.kiro.region`
- **AND** no `--identity-provider` or `--region` flags are passed
- **THEN** the transport SHALL use the config file values for identity provider and region

#### Scenario: Missing config file
- **WHEN** `install.sh` runs with `--config /nonexistent/path`
- **THEN** the script SHALL exit with a non-zero status and print an error indicating the file does not exist or is not readable

#### Scenario: Ambient environment variable ignored when unset elsewhere
- **WHEN** the invoking shell has `GA_MACHINE_NAME=from-env` exported, no `--config` file is passed, and no corresponding flag is passed
- **THEN** `install.sh` SHALL use the built-in default (`ghost-academy`), not the ambient value `from-env`

#### Scenario: Repository and XDG layers apply without --config
- **WHEN** `--config` is absent and repo-level or XDG configuration files provide overrides
- **THEN** values resolve as built-in defaults, then `config/ghostship.yaml`, then the XDG override

### Requirement: Install migrates legacy config

Before reading config, `install.sh` SHALL migrate `config/ghostship.conf` when no YAML counterpart exists and print a migration notice.

#### Scenario: Legacy ghostship.conf is migrated during install
- **WHEN** `install.sh` finds `config/ghostship.conf` and no `config/ghostship.yaml`
- **THEN** it migrates the conf file to YAML and prints a migration notice
### Requirement: Configuration documentation covers YAML settings

`docs/configuration.md` SHALL document the YAML format, supported keys by section, merge order, repo and XDG locations, override-only usage, and the migration from `ghostship.conf`, which is no longer read.

#### Scenario: Config file section present in docs
- **WHEN** reading `docs/configuration.md`
- **THEN** it contains a section explaining the YAML format, all supported keys, and the three-layer resolution order

#### Scenario: Migration path documented
- **WHEN** reading `docs/configuration.md`
- **THEN** it describes the auto-migration from `ghostship.conf` to `ghostship.yaml` and states that `ghostship.conf` is no longer read

#### Scenario: No ambient environment variable tier documented
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL NOT describe exporting a shell variable as a supported configuration method

#### Scenario: Removed vars absent from docs
- **WHEN** reading `docs/configuration.md`
- **THEN** the removed variables SHALL NOT appear as supported operator-configurable inputs

#### Scenario: Documentation lists config paths and override behavior
- **WHEN** reading `docs/configuration.md`
- **THEN** it identifies the repo-level and XDG files and explains that config files contain only keys the operator wants to change

### Requirement: Configuration documentation records model precedence

The docs SHALL state the model precedence chain: `dispatch(model=...)` > `model.override` > per-agent model > `model.default` > KiroCrew built-in.

#### Scenario: Model precedence table present in docs
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL include a model precedence table or section documenting: `dispatch(model=...)` > `model.override` > per-agent model > `model.default` > KiroCrew built-in

### Requirement: Configuration documentation records knowledge auto-ingest posture

The docs SHALL explain that Ghostship does not enable auto-ingest, that operators must opt in to worktree ingestion, and that the disabled posture relies on verified upstream defaults with a CI regression guard rather than a config pin.

#### Scenario: Knowledge auto-ingest posture documented
- **WHEN** an operator reads the knowledge section of `docs/configuration.md`
- **THEN** they learn that auto-ingest is off by the verified upstream default, that it is
  deliberately NOT pinned (no `knowledge.auto_ingest` key exists to pin), that a CI test
  guards against an upstream default flip, and how to opt in explicitly if wanted

#### Scenario: Knowledge note records verified upstream defaults
- **WHEN** an operator reads the knowledge auto-ingest note
- **THEN** it says KiroCrew 0.9.0+ (PR #2448) makes artifact watching and auto-add-documents opt-in; the actual `knowledge.auto_ingest_artifacts` and `knowledge.auto_add_documents` toggles default to false; no single `knowledge.auto_ingest` boolean exists to pin; an upstream default flip is guarded by `tests/unit/test_trn223_knowledge_autoingest.py`; and worktree ingestion requires explicit opt-in
### Requirement: Transport runtime config centralised in Config dataclass
The transport SHALL load all runtime configuration from environment variables exactly once at startup into a `Config` dataclass defined in `transport/config.py`. All transport subsystems SHALL read configuration from this loaded instance rather than calling `os.environ.get()` directly at use sites.

#### Scenario: Config loaded at startup
- **WHEN** the transport process starts
- **THEN** a single `Config` instance is constructed from the current environment variables before any request is handled

#### Scenario: Default values applied consistently
- **WHEN** an environment variable is absent
- **THEN** the `Config` dataclass applies the same default that was previously scattered at each call site

### Requirement: Config fields match ghostship.yaml.example
Every field in the `Config` dataclass SHALL have a corresponding commented-out entry
in `config/ghostship.yaml.example`, and vice versa. A CI test SHALL assert this
invariant. `config/ghostship.conf.example` is retired.

#### Scenario: CI sync check passes
- **WHEN** `Config` fields and `ghostship.yaml.example` entries are in sync
- **THEN** the CI test passes

#### Scenario: CI sync check fails on drift
- **WHEN** a field is added to `Config` without a matching entry in `ghostship.yaml.example`
- **THEN** the CI test fails and identifies the missing entry

### Requirement: Operator-configurable git author identity for crew commits
The system SHALL optionally inject `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and `GIT_COMMITTER_EMAIL` environment variables into crew containers at creation time when `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are set. When set, all commits made by agents inside the crew SHALL carry the operator's configured identity as both author and committer.

#### Scenario: Git identity injected when configured
- **WHEN** `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL` are set and a crew is launched
- **THEN** the crew container has all four git identity env vars set to the configured values

#### Scenario: Identity not injected when unconfigured
- **WHEN** `GA_GIT_AUTHOR_NAME` is unset
- **THEN** the crew container does not have `GIT_AUTHOR_NAME` or `GIT_COMMITTER_NAME` in its environment — kiro-cli uses its own per-session identity

### Requirement: Configuration docs explain GA_FILE_SECRET

The `GA_FILE_SECRET` row SHALL explain that the transport generates and persists it at `DATA_DIR/ga-file-secret` on first start; it is not passed through compose and needs no operator override.

#### Scenario: Operator reads GA_FILE_SECRET docs
- **WHEN** an operator reads the `GA_FILE_SECRET` entry in `docs/configuration.md`
- **THEN** they understand that the value is auto-generated by the transport on first start, not passed through compose, and no override is needed

### Requirement: Configuration docs explain TRANSPORT_DATA_DIR

The `TRANSPORT_DATA_DIR` row SHALL state that standard installs use `/data` because `DATA_DIR` is mounted there, and changing it requires a custom compose override.

#### Scenario: Operator reads TRANSPORT_DATA_DIR docs
- **WHEN** an operator reads the `TRANSPORT_DATA_DIR` entry in `docs/configuration.md`
- **THEN** they understand that the effective value is `/data` in the standard install and cannot be changed without a custom compose override
### Requirement: GA_MAX_ACTIVE_CREWS documents zero-and-negative-disable semantics

`docs/configuration.md` and `config/ghostship.conf.example` SHALL document that any value ≤ 0 for `GA_MAX_ACTIVE_CREWS` disables the active-crew limit (not only `0`).

#### Scenario: Operator reads GA_MAX_ACTIVE_CREWS docs
- **WHEN** an operator reads the `GA_MAX_ACTIVE_CREWS` entry in `docs/configuration.md`
- **THEN** they see "Set to 0 (or any value ≤ 0) to disable the active-crew limit"

### Requirement: _TASK_TIMESTAMP_TTL_SECS comment is accurate

The comment block above `_TASK_TIMESTAMP_TTL_SECS` in `transport/lifecycle.py` SHALL accurately describe the floor behaviour: `_warm_marker_ttl_secs()` enforces a one-hour floor; `_TASK_TIMESTAMP_TTL_SECS` does not. The comment SHALL NOT claim a floor that does not exist.

#### Scenario: Code comment matches actual behaviour
- **WHEN** a developer reads the `_TASK_TIMESTAMP_TTL_SECS` comment in `lifecycle.py`
- **THEN** the comment accurately states which TTL has a floor and which does not, matching the actual code behaviour

### Requirement: Auth docs describe the auth command
`docs/auth.md` SHALL state that backend credentials are not configured in `ghostship.conf`, SHALL keep the config-file snippet for `KIRO_IDENTITY_PROVIDER`/`KIRO_REGION` as the Identity Center default, and SHALL document `ghostship auth login <kiro|claude|codex>`, its methods, `ghostship auth logout <backend>` and `ghostship auth status`.

#### Scenario: Auth docs reference the auth command
- **WHEN** reading `docs/auth.md`
- **THEN** it describes each backend's login methods under `ghostship auth login`, including that Identity Center defaults to the configured start URL and region, and contains no credential snippet for `ghostship.conf`
