# captain Specification

## Purpose

Defines the behaviour of the `captain` MCP tool — the control interface for managing the crew's persistent check-in schedule, including how stop operations interact with the gateway cron and the ghostship schedule registry.

## Requirements

### Requirement: captain stop always disables the schedule registry entry

When `captain(action="stop")` is called, the ghostship schedule registry entry for the captain check-in job SHALL be updated to `enabled: false` unconditionally — regardless of the job's current state in the KiroCrew gateway. The registry update SHALL NOT be skipped when the gateway already reports the job as disabled.

#### Scenario: captain stop when gateway cron is already disabled

- **WHEN** `captain(action="stop")` is called and the captain check-in job's gateway cron is already `enabled: false` (e.g. Raven paused it via CLI)
- **THEN** the ghostship registry entry is updated to `enabled: false`
- **THEN** the crew is eligible for idle-stop — the gateway already shows `enabled: false`, so the idle monitor's `_cron_has_enabled_job` check passes and the crew stops after `GA_IDLE_TIMEOUT_SECS` with no other activity

#### Scenario: captain stop when gateway cron is enabled

- **WHEN** `captain(action="stop")` is called and the captain check-in job's gateway cron is `enabled: true`
- **THEN** the transport calls the gateway cron disable API AND updates the registry to `enabled: false`
- **THEN** the crew is eligible for idle-stop after `GA_IDLE_TIMEOUT_SECS` with no other activity

### Requirement: Configurable user-defined orders directory

The system SHALL support a `GA_ORDERS_DIR` environment variable that points to an operator-managed directory of additional standing-order template files. When set and the directory exists, its `.md` files SHALL be merged with the built-in `academy/orders/` templates to form the effective template set. A user-defined template whose filename stem matches a built-in template name SHALL override (take precedence over) the built-in template. Built-in templates with no user-defined counterpart remain available unchanged.

When `GA_ORDERS_DIR` is unset or its path does not exist, the system SHALL behave exactly as before, using only the built-in `academy/orders/` templates.

#### Scenario: GA_ORDERS_DIR adds new templates
- **WHEN** `GA_ORDERS_DIR` points to a directory containing `deploy.md` and `audit.md`
- **THEN** `captain(action="order", template="deploy")` and `captain(action="order", template="audit")` are accepted, and the templates are resolved from the user-defined directory

#### Scenario: User-defined template overrides a built-in
- **WHEN** `GA_ORDERS_DIR` points to a directory containing `sdd.md`
- **THEN** `captain(action="order", template="sdd")` resolves the user-defined `sdd.md` instead of the built-in `academy/orders/sdd.md`

#### Scenario: GA_ORDERS_DIR unset — behaviour unchanged
- **WHEN** `GA_ORDERS_DIR` is not set
- **THEN** only the built-in `academy/orders/` templates are available, and all existing captain behaviour is preserved

#### Scenario: GA_ORDERS_DIR path does not exist
- **WHEN** `GA_ORDERS_DIR` is set to a path that does not exist on the filesystem
- **THEN** the system logs a warning and falls back to built-in templates only — no error is raised at transport startup or at template load time

#### Scenario: Built-in templates remain available when GA_ORDERS_DIR is set
- **WHEN** `GA_ORDERS_DIR` is set and does NOT contain a file named `independent-review.md`
- **THEN** `captain(action="order", template="independent-review")` still resolves the built-in template from `academy/orders/`

### Requirement: Captain dispatch uses a compatible model on Claude-backend crews

When the system dispatches a Captain check-in on a crew whose configured
`acp_backend` is `"claude"` (or whose crew-level default model is a Claude model),
and no explicit model override is provided by the Captain order, the system SHALL
derive the dispatch model from the crew's configured default model rather than
relying on the `raven.json` `"model"` field. This ensures Raven is always dispatched
on a model that is compatible with the backend's capabilities.

The `raven.json` `"model"` field is a default for non-Claude backend crews; it SHALL
NOT be used as the dispatch model when the crew runs on a Claude backend.

#### Scenario: Captain check-in on Claude-backend crew uses crew model

- **WHEN** `_dispatch_captain_checkin` is called for a crew with `acp_backend="claude"`
  and the caller passes `model=None`
- **THEN** the spawn request includes `"model": <crew_default_model>` derived from the
  crew's registry entry, not a GPT model string from `raven.json`

#### Scenario: Explicit model override is respected

- **WHEN** `_dispatch_captain_checkin` is called with an explicit non-None `model`
  parameter
- **THEN** the spawn request uses that explicit model, regardless of the crew's
  configured backend or default model

#### Scenario: Non-Claude crew unaffected

- **WHEN** `_dispatch_captain_checkin` is called for a crew that does not use the
  Claude backend, with `model=None`
- **THEN** the spawn request is built exactly as before (no `"model"` key from the
  crew registry is added; gateway picks the default)
