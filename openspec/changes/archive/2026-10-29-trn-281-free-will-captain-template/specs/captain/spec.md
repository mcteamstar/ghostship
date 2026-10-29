## MODIFIED Requirements

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
