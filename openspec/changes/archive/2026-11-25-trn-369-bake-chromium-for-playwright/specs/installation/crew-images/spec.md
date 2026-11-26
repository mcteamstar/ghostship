# Spec Delta

## ADDED Requirements

### Requirement: Spec-ops exposes Playwright to Ghost
The `spec-ops` composition SHALL select the existing `playwright` MCP catalogue entry, and the Ghost persona SHALL receive the `@playwright` tool grant. Fresh crew setup SHALL activate the selected MCP through Academy and the harness setup flow.

#### Scenario: Fresh spec-ops crew receives Playwright
- **WHEN** an operator launches a fresh `spec-ops` crew
- **THEN** the crew's native harness MCP configuration contains an active Playwright server resolved from `academy/mcp/playwright.json`
- **AND** Ghost's persona spec contains the Playwright server entry in `mcpServers`
- **AND** Ghost's tool grants include `@playwright`

#### Scenario: Other personas do not receive the Playwright grant
- **WHEN** the standard agent definitions are loaded
- **THEN** only Ghost receives the `@playwright` tool grant as part of this change

### Requirement: Academy projects selected MCP entries into ACP personas
For each selected persona, Academy SHALL add a selected composition MCP entry to `mcpServers` only when the persona's `tools` grant references that server. An explicit persona-level entry SHALL take precedence over a composition entry with the same name.

#### Scenario: ACP persona receives its selected server
- **WHEN** a selected persona references a selected composition server in its `tools` grant
- **THEN** Academy includes the resolved server in the persona's `mcpServers` map for ACP session setup

#### Scenario: Unreferenced personas do not receive a composition server
- **WHEN** a composition server is selected but a persona's `tools` list does not reference it
- **THEN** Academy does not add that server to the persona's `mcpServers` map

#### Scenario: Explicit persona config takes precedence
- **WHEN** a persona already defines a selected server in its own `mcpServers` map
- **THEN** Academy preserves the persona's entry instead of replacing it with the composition entry

### Requirement: Fresh spec-ops crews launch local Chromium through Playwright
A fresh `spec-ops` crew SHALL use the configured Playwright MCP as `kirocrew` to launch headless Chromium and read a local page without a first-use browser download. The browser SHALL remain accessible when the crew home is mounted as a volume. The image SHALL contain the browser and required runtime dependencies if its existing contents do not satisfy these conditions.

#### Scenario: Fresh crew opens a local page
- **WHEN** Ghost uses Playwright MCP in a fresh crew to navigate to a local `data:` page
- **THEN** Playwright launches Chromium and returns the page title and body
- **AND** browser binaries are not downloaded at first use

#### Scenario: Crew home volume does not hide the browser
- **WHEN** the crew runs with `/home/kirocrew` mounted from a crew home volume
- **THEN** Playwright can still resolve and launch its compatible Chromium browser

#### Scenario: Browser smoke check passes on supported image architectures
- **WHEN** the spec-ops image is built for a supported architecture
- **THEN** the fresh-crew Playwright smoke check passes as `kirocrew` under normal container restrictions
