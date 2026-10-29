## Purpose

The `free-will` built-in order template (aliases: `free`, `willy`) enables open-ended
autonomous captaincy. It formalises the default behaviour of passing a raw message to
the Captain without a structured lifecycle, giving it a discoverable name and consistent
scaffolding.

## ADDED Requirements

### Requirement: free-will template is available as a built-in order template

`academy/orders/free-will.md` SHALL exist and be discoverable via the order template
index. The template front-matter SHALL declare `aliases: ["free", "willy"]` and a
human-readable description. The `captain` tool SHALL accept `template="free-will"`,
`template="free"`, and `template="willy"` as equivalent invocations.

#### Scenario: free-will resolves by primary name
- **WHEN** `captain(template="free-will", message="do X")` is called
- **THEN** the template body is loaded and the `<message>` placeholder is substituted
  with "do X"

#### Scenario: free-will resolves by alias "free"
- **WHEN** `captain(template="free", message="do X")` is called
- **THEN** the template resolves identically to `template="free-will"`

#### Scenario: free-will resolves by alias "willy"
- **WHEN** `captain(template="willy", message="do X")` is called
- **THEN** the template resolves identically to `template="free-will"`

### Requirement: free-will template substitutes the standing order message

The `free-will` template body SHALL contain a `<message>` placeholder that is
substituted with the value of the `message` parameter before the resolved text is
delivered to the Captain mailbox.

#### Scenario: message substitution applied
- **WHEN** `captain(template="willy", message="investigate disk usage on the crew")` is called
- **THEN** the Captain mailbox receives text containing "investigate disk usage on the crew"
  where `<message>` appeared in the template

### Requirement: free-will template lists in the order template index

`transport://orders` (the MCP resource listing available templates) SHALL include an
entry for `free-will` with its description.

#### Scenario: free-will appears in template listing
- **WHEN** the `transport://orders` resource is read
- **THEN** an entry named `free-will` is present with a non-empty description
