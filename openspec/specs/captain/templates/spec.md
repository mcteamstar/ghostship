# captain/templates Specification

## Purpose

Defines standing order discovery, rendering and shared template policies.

## Requirements

### Requirement: Standing orders can be composed from a named template
The system SHALL maintain a small, fixed registry of named standing-order templates. When `captain(crew_id, action="order", template=<name>, ...)` is called, the system SHALL resolve `<name>` to that template's text, substituting `change_name` where the template requires it, and SHALL treat the resolved text exactly as a hand-written `message` for every purpose downstream (mailbox write, check-in job creation/reuse). An unknown template name SHALL be rejected before any mail is written.

#### Scenario: Ordering with the built-in SDD template
- **WHEN** `captain(crew_id, action="order", template="sdd", change_name=<name>, interval=<n>)` is called
- **THEN** the system resolves the `"sdd"` template, names `<name>` in it, writes the result to `captain@localhost`, and ensures a recurring check-in exists exactly as it would for an equivalent hand-written `message`

#### Scenario: Unknown template name
- **WHEN** `captain(crew_id, action="order", template=<unknown-name>, ...)` is called
- **THEN** the system returns an error naming the unknown template and writes no mail

### Requirement: Captain order templates are filesystem-backed
The system SHALL load standing-order templates from individual Markdown files
located in `academy/orders/<name>.md` rather than from the hardcoded
`_ORDER_TEMPLATES` dictionary in `transport/server.py`.

Each template file SHALL contain the raw template body with placeholders.
Template metadata (name, description) SHALL be derived from the filename and
an optional YAML front-matter `description` field.

#### Scenario: Template loaded from academy/orders/
- **WHEN** transport resolves a captain order with `template="sdd"`
- **THEN** the system reads `academy/orders/sdd.md` from the configured academy path and uses its content as the template body

#### Scenario: Template file not found
- **WHEN** transport resolves a captain order with a template name that has no corresponding file in `academy/orders/`
- **THEN** the system raises a ValueError with the message `Unknown Captain order template: '<name>'`

### Requirement: Template placeholder contract
Template files SHALL support the following placeholders, substituted at
resolution time by the transport:

| Placeholder | Resolved to |
|---|---|
| `{{RAVEN_GATEWAY_ORIENTATION}}` | The gateway orientation paragraph (CLI vs REST, credential path) |
| `{{RAVEN_STORE_RESOLUTION}}` | The OpenSpec store registration guidance |
| `{{RAVEN_SELF_CANCEL}}` | The self-cancel instruction for Raven |
| `<change>` | The `change_name` argument passed to `_resolve_order_template` |

#### Scenario: All placeholders resolved
- **WHEN** a template containing all four placeholders is resolved with `change_name="my-change"`
- **THEN** the resolved body contains the full text of each constant and the literal string `my-change` in place of `<change>`

#### Scenario: Missing change_name when template uses <change>
- **WHEN** a template containing `<change>` is resolved with `change_name=None`
- **THEN** the system raises a ValueError indicating that `change_name` is required

### Requirement: transport://orders resource lists templates dynamically
The `transport://orders` MCP resource SHALL enumerate available templates by
scanning the `academy/orders/` directory at call time, returning each
template's name (derived from filename without extension) and description.

#### Scenario: Resource lists all available templates
- **WHEN** a client reads the `transport://orders` resource
- **THEN** the response includes one section per `.md` file found in `academy/orders/`, with the template name and its full body

#### Scenario: No templates on disk
- **WHEN** `academy/orders/` is empty or does not exist
- **THEN** the resource returns `No standing-order templates are available.`

### Requirement: captain tool description lists free-will as a built-in template

The `captain` MCP tool description SHALL list `free-will` / `free` / `willy` as a
built-in template alongside `spec-driven-development` / `sdd` / `specky` and
`independent-review` / `indy`.

#### Scenario: captain tool docstring includes free-will
- **WHEN** the `captain` tool description is read (e.g. via `/openapi.json` or the
  MCP tool listing)
- **THEN** the text includes `free-will` and its aliases `free` and `willy`
- **THEN** the description explains that `free-will` is the open-ended autonomous
  template

### Requirement: User orders directory adds templates

When `GA_ORDERS_DIR` names an existing directory, its `.md` templates SHALL be merged with built-in `academy/orders/` templates; built-in templates without an override SHALL remain available.

#### Scenario: GA_ORDERS_DIR adds new templates
- **WHEN** `GA_ORDERS_DIR` points to a directory containing `deploy.md` and `audit.md`
- **THEN** `captain(action="order", template="deploy")` and `captain(action="order", template="audit")` are accepted, and the templates are resolved from the user-defined directory

#### Scenario: Built-in templates remain available when GA_ORDERS_DIR is set
- **WHEN** `GA_ORDERS_DIR` is set and does NOT contain a file named `independent-review.md`
- **THEN** `captain(action="order", template="independent-review")` still resolves the built-in template from `academy/orders/`

### Requirement: User templates override matching built-ins

A user-defined template whose filename stem matches a built-in name SHALL take precedence over that built-in.

#### Scenario: User-defined template overrides a built-in
- **WHEN** `GA_ORDERS_DIR` points to a directory containing `sdd.md`
- **THEN** `captain(action="order", template="sdd")` resolves the user-defined `sdd.md` instead of the built-in `academy/orders/sdd.md`

### Requirement: Missing user orders directory preserves defaults

When `GA_ORDERS_DIR` is unset or its path does not exist, the system SHALL use only built-in `academy/orders/` templates.

#### Scenario: GA_ORDERS_DIR unset — behaviour unchanged
- **WHEN** `GA_ORDERS_DIR` is not set
- **THEN** only the built-in `academy/orders/` templates are available, and all existing captain behaviour is preserved

#### Scenario: GA_ORDERS_DIR path does not exist
- **WHEN** `GA_ORDERS_DIR` is set to a path that does not exist on the filesystem
- **THEN** the system logs a warning and falls back to built-in templates only — no error is raised at transport startup or at template load time

### Requirement: Order templates preserve retry state after memory refusal

The SDD and independent-review templates SHALL treat a memory-pressure refusal as a failed spawn: write no confirmation, keep the pending intent, do not retry in the same cycle, and retry on a later check-in.

#### Scenario: Raven holds and retries on a memory-pressure refusal
- **WHEN** Raven issues `POST /api/spawn` and receives a memory-pressure refusal (HTTP 503 or 429 whose body names memory pressure)
- **THEN** Raven writes no dispatch confirmation and leaves the pending intent marker active
- **THEN** Raven does NOT treat the cycle as a completed dispatch

### Requirement: Order templates escalate sustained memory refusals

Templates SHALL count consecutive memory-pressure refusals and, at the configured threshold, mail the Admiral with the sustained-pressure subject and actual crew ID before holding.

#### Scenario: Raven escalates after sustained memory-pressure refusals
- **WHEN** Raven has observed `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` consecutive memory-pressure refusals for the same dispatch intent
- **THEN** Raven mails `admiral@localhost` with subject `captain check-in deferred — sustained memory pressure <crew_id>` (substituting the actual crew id)
- **THEN** Raven holds and does not attempt another spawn in the same cycle
