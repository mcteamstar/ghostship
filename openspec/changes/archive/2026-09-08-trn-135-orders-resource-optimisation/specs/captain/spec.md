## ADDED Requirements

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
