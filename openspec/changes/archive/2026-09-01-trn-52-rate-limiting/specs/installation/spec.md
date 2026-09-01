## MODIFIED Requirements

### Requirement: Rate limiting env vars documented in configuration docs

`docs/configuration.md` SHALL include a "Rate Limiting" section that documents all six
`GA_RATE_LIMIT_*` environment variables introduced by TRN-52: their names, the
`<count>:<window_secs>` format, the default value for each, and the behaviour on
parse failure. The section SHALL note that rate limiter state is held in memory and
resets on process restart.

#### Scenario: Operator consults docs to tune /mcp rate limit
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find a table or list of all `GA_RATE_LIMIT_*` variables with their
  defaults and format, and can set `GA_RATE_LIMIT_MCP=600:120` with confidence

### Requirement: Rate limiting env vars included in example config

`config/ghostship.conf.example` SHALL include commented-out entries for all six
`GA_RATE_LIMIT_*` variables, each showing its default value in `<count>:<window_secs>`
format (or `true`/`false` for the master switch). Comments SHALL explain the format.

#### Scenario: Operator copies example config to customise limits
- **WHEN** an operator copies `config/ghostship.conf.example` to customise their
  installation
- **THEN** the `GA_RATE_LIMIT_*` entries are present, commented out, and show the
  correct default values
