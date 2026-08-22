## MODIFIED Requirements

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

Placeholders SHALL use the double-brace `{{…}}` syntax for transport-injected
constants, distinguishing them from the existing `<change>` substitution which
remains angle-bracket-delimited for backward compatibility.

#### Scenario: All placeholders resolved
- **WHEN** a template containing `{{RAVEN_GATEWAY_ORIENTATION}}`, `{{RAVEN_STORE_RESOLUTION}}`, `{{RAVEN_SELF_CANCEL}}`, and `<change>` is resolved with `change_name="my-change"`
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

### Requirement: Captain tool interface unchanged
The captain MCP tool's interface (parameter names, types, return value) SHALL
NOT change. The only difference is the backing store for templates.

#### Scenario: Existing captain(order) call works identically
- **WHEN** a caller invokes `captain(order=True, template="sdd", change_name="my-change")`
- **THEN** the resolved standing order is delivered to `captain@localhost` with identical content to what the old `_ORDER_TEMPLATES["sdd"]` dict would have produced
