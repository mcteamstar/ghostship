# Spec Delta

## MODIFIED Requirements

### Requirement: YAML config schema with logical sections
The YAML config SHALL be organised into logical top-level sections. Configuration
under optional `backends.claude` or `backends.codex` SHALL also declare that backend
enabled for toolchain installation. Kiro SHALL remain a built-in enabled backend.
`backends.default` SHALL be a scalar backend name selecting the implicit runtime
backend, defaulting to Kiro when omitted; it SHALL not be a list of enabled backends.

#### Scenario: Full config structure accepted
- **WHEN** `config/ghostship.yaml` contains all sections with valid values
- **THEN** install.sh SHALL parse and apply all values without error

#### Scenario: Unknown keys warned
- **WHEN** `config/ghostship.yaml` contains an unrecognised key
- **THEN** install.sh SHALL warn the operator and continue without aborting

#### Scenario: backends.default as scalar
- **WHEN** `config/ghostship.yaml` sets `backends.default: claude` and contains `backends.claude: {}`
- **THEN** `GA_CREW_AGENT` SHALL be derived as `claude,kiro`

#### Scenario: Missing default uses Kiro
- **WHEN** `config/ghostship.yaml` omits `backends.default`
- **THEN** Kiro SHALL be the implicit runtime backend

#### Scenario: Legacy list is rejected
- **WHEN** `config/ghostship.yaml` sets `backends.default: [kiro, claude]`
- **THEN** install.sh SHALL fail with migration guidance

## MODIFIED Requirements

### Requirement: Backend model defaults avoid automatic routing
Shipped backend profiles SHALL provide concrete model defaults while leaving shipped
persona definitions unpinned. The harness `auto` fallback SHALL remain available when
an operator explicitly clears the relevant backend model default.

#### Scenario: Kiro backend default
- **WHEN** a Kiro crew has no higher-precedence model selection
- **THEN** Ghostship uses `claude-haiku-5.5` rather than automatic routing

#### Scenario: Claude backend default
- **WHEN** a Claude crew has no higher-precedence model selection
- **THEN** Ghostship uses `claude-haiku-5-5` rather than automatic routing

#### Scenario: Codex backend default
- **WHEN** a Codex crew has no higher-precedence model selection
- **THEN** Ghostship uses `gpt-6-luna` rather than automatic routing

#### Scenario: Explicitly cleared default delegates to harness
- **WHEN** an operator explicitly clears the selected backend's model default and no higher-precedence model applies
- **THEN** Ghostship SHALL supply `auto` rather than silently inserting a concrete model

#### Scenario: Explicit selection retains precedence
- **WHEN** a dispatch model or backend override is supplied
- **THEN** that explicit selection SHALL take precedence over the backend default

#### Scenario: Rejected pin is distinct from unset selection
- **WHEN** the runtime rejects a configured backend model
- **THEN** the resulting harness-selected model SHALL be reported as a rejected configured pin, not as the normal configured fallback

## ADDED Requirements

### Requirement: Backend default has scalar compatibility semantics
`backends.default` SHALL accept a scalar backend name. The legacy list form SHALL
not silently select multiple enabled backends; install.sh SHALL reject it with a
migration error or provide an explicit, documented migration to a scalar default
and backend sections.

#### Scenario: Scalar default accepted
- **WHEN** `backends.default: claude` is configured
- **THEN** the generated runtime configuration SHALL identify Claude as the implicit backend

#### Scenario: Legacy list rejected or migrated
- **WHEN** `backends.default: [claude, kiro]` is configured
- **THEN** install.sh SHALL either fail with an actionable migration message or convert it to `default: claude` while enabling the corresponding backend sections
