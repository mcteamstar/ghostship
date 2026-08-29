## ADDED Requirements

### Requirement: Transport runtime config centralised in Config dataclass
The transport SHALL load all runtime configuration from environment variables exactly once at startup into a `Config` dataclass defined in `transport/config.py`. All transport subsystems SHALL read configuration from this loaded instance rather than calling `os.environ.get()` directly at use sites.

#### Scenario: Config loaded at startup
- **WHEN** the transport process starts
- **THEN** a single `Config` instance is constructed from the current environment variables before any request is handled

#### Scenario: Default values applied consistently
- **WHEN** an environment variable is absent
- **THEN** the `Config` dataclass applies the same default that was previously scattered at each call site

### Requirement: Config fields match ghostship.conf.example
Every field in the `Config` dataclass SHALL have a corresponding commented-out entry in `config/ghostship.conf.example`, and vice versa. A CI test SHALL assert this invariant so the two cannot silently diverge.

#### Scenario: CI sync check passes
- **WHEN** `Config` fields and `ghostship.conf.example` entries are in sync
- **THEN** the CI test passes

#### Scenario: CI sync check fails on drift
- **WHEN** a field is added to `Config` without a matching entry in `ghostship.conf.example`
- **THEN** the CI test fails and identifies the missing entry
