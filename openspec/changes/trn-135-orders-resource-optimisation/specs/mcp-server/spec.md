## MODIFIED Requirements

### Requirement: Order template resource

The system SHALL expose the following MCP resources for standing-order template discovery and retrieval:

**Summary index — `transport://orders`**
The system SHALL expose a `transport://orders` MCP resource that returns a lightweight index of all available standing-order templates — built-in and user-defined. Each entry SHALL include only the template name and its one-line description. The full body of any template SHALL NOT be included in this response.

**Per-template resource — `transport://orders/{name}`**
The system SHALL expose a `transport://orders/{name}` MCP resource for each available template. When read, it SHALL return the template's complete resolved body exactly as `captain(action="order", template=<name>, ...)` would use it — with all placeholder substitutions applied and the front-matter description stripped from the body. If the requested template does not exist, the resource SHALL return an appropriate error or 404-equivalent response rather than an empty body.

Both resources SHALL remain available without any running crew, since templates are static transport-side content.

#### Scenario: Templates present

- **WHEN** `transport://orders` is read and one or more templates are available
- **THEN** the response is a plain-text summary index — one entry per template showing the template name and its one-line description; the full template body text is NOT included

#### Scenario: Reading the resource requires no crew

- **WHEN** `transport://orders` or `transport://orders/{name}` is read
- **THEN** the response does not depend on any crew existing or being reachable, since templates are static transport-side content

#### Scenario: transport://orders/{name} returns full resolved body

- **WHEN** `transport://orders/sdd` is read
- **THEN** the response contains the complete resolved body of the `sdd` template with all `{{PLACEHOLDER}}` tokens substituted, and without the YAML front-matter block

#### Scenario: transport://orders/{name} for unknown template

- **WHEN** `transport://orders/nonexistent` is read
- **THEN** the resource returns an error indicating the template was not found, rather than an empty or partial response

#### Scenario: User-defined template appears in summary index

- **WHEN** `GA_ORDERS_DIR` is set, a user-defined template named `my-workflow` exists in that directory, and `transport://orders` is read
- **THEN** `my-workflow` appears in the summary index alongside built-in templates

#### Scenario: User-defined template is readable via per-template resource

- **WHEN** `GA_ORDERS_DIR` is set, a user-defined template named `my-workflow` exists, and `transport://orders/my-workflow` is read
- **THEN** the response contains the full resolved body of `my-workflow`

#### Scenario: Reading the resources requires no crew

- **WHEN** either `transport://orders` or `transport://orders/{name}` is read
- **THEN** the response does not depend on any crew existing or being reachable