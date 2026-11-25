# installation/crew-images Specification

## Purpose

Defines crew image construction, versioning and installation.

## Requirements

### Requirement: Base-image pin tracks the target KiroCrew gateway version

The admission build and shipped configuration SHALL default to the verified
KiroCrew `0.13.1` multi-architecture digest. Before release, maintainers SHALL
inspect the stable image, verify its bundled Kiro CLI and seed schema, and smoke
test fresh crews. The `KC_BASE_IMAGE` comment SHALL record the gateway version,
CLI version, digest, and verification date.

#### Scenario: operator builds with the default base image

- **WHEN** an operator builds the crew image without overriding the base-image
  selection
- **THEN** the admission image builds from the pinned KiroCrew gateway version
- **AND** the resulting crew runs that gateway version.

#### Scenario: build definition and configuration default stay in sync

- **WHEN** the base-image pin is changed in the build definition
- **THEN** the configuration default SHALL be updated to the same value in the
  same change
- **AND** a plain build with no override and an install build resolve to the
  identical base image.

#### Scenario: pin prefers an immutable reference

- **WHEN** the target gateway version is published both as a floating tag and as
  an immutable digest
- **THEN** the pin SHOULD use the immutable digest
- **SO THAT** a later rebuild cannot float onto a different published image
  without an explicit change.

#### Scenario: operator builds with an explicit base-image override

- **WHEN** an operator explicitly overrides `KC_BASE_IMAGE` after this change is
  applied
- **THEN** that build uses the explicit override
- **AND** a build without an override continues to use the pinned default.

#### Scenario: release uses the verified stable pin

- **WHEN** a Ghostship release targeting KiroCrew 0.13.1 is prepared
- **THEN** the `KC_BASE_IMAGE` default names the verified stable `0.13.1` index
  digest
- **AND** image inspection, seed verification and fresh-crew smoke checks have
  passed against that image.

#### Scenario: login containers use the pinned image

- **WHEN** an operator runs a backend login after this change is applied
- **THEN** the ephemeral login container runs the same pinned KiroCrew image as
  new crews
- **AND** the Kiro CLI that captures the kiro credential is the image's bundled
  version.

### Requirement: kiro-cli DB seed matches the base-image migration schema

The CLI seed SHALL match the pinned image’s active chat runtime migration rows
and SQLite schema, including `auth_kv` and `state`, so launch can inject auth
without waiting for migrations. Each pin change SHALL reverify these against
the image or its published layers. The seed annotation SHALL record the gateway
and CLI versions, verification date, migration count, and maximum version.

#### Scenario: seed verified and matching the base image

- **WHEN** the base image's kiro-cli migration table reports a migration count and
  maximum version
- **AND** the seed pre-seeds exactly those migration rows and that table schema
- **THEN** the auth-injection step finds the authentication table present with the
  expected columns and the auth insert succeeds
- **AND** agents authenticate on first launch with no migration or restart cycle.

#### Scenario: base-image migration schema unchanged from the prior pin

- **WHEN** the newly pinned base image reports the same migration count, maximum
  version, and table set as the previously verified base image
- **THEN** the seed's migration rows and table-creation statements remain unchanged
- **AND** only the seed's verification annotation is updated to record the new
  verified version and date.

#### Scenario: base-image migration schema changed from the prior pin

- **WHEN** the newly pinned base image reports a different migration count, maximum
  version, or table set than the previously verified base image
- **THEN** the seed MUST be updated so its migration rows span every version the
  base image reports and its table-creation statements reflect every added,
  removed, or altered table before the image is released
- **AND** the authentication table MUST remain present with the columns the
  auth-injection step requires.

#### Scenario: base image bumped without re-verifying the seed (regression guard)

- **WHEN** the base-image pin is advanced to a new gateway version whose migration
  schema differs from the seed
- **AND** the seed is not re-verified or updated
- **THEN** the crew image still builds with no build-time error
- **BUT** the auth-injection step fails at launch (for example, a missing
  authentication table or an incomplete auth insert) and agents cannot
  authenticate.
- The re-verification of the seed against the newly pinned base image is therefore
  a release gate, not optional.

#### Scenario: v0.12.2 chat schema is fully pre-seeded

- **WHEN** the previously pinned v0.12.2 image's active chat runtime is initialized
- **THEN** its seed contained 11 migration rows for versions 0 through 10
- **AND** that baseline is what the newly pinned image's schema is compared
  against when deciding whether the seed must change.

#### Scenario: injected Identity Center credential carries its profile

- **WHEN** a kiro IAM Identity Center credential that includes
  `api.codewhisperer.profile` is injected into a fresh crew built on the pinned
  image
- **THEN** the profile row lands in the seeded `state` table
- **AND** a kiro task on that crew completes without a "No profile selected"
  error.

### Requirement: OpenSpec Node runtime satisfies the gateway Node floor

The spec-ops crew image SHALL install a Node runtime that meets or exceeds the Node
version floor required by the pinned KiroCrew gateway, for the OpenSpec CLI layer,
and this runtime SHALL be independent of the gateway's own internal Node runtime.
The Node installer SHALL be integrity-checked so that a drift in the upstream
installer is detected at build time.

#### Scenario: Node runtime meets the gateway floor

- **WHEN** the crew image is built for a gateway version with a given Node version
  floor
- **THEN** the spec-ops image installs a Node runtime at or above that floor for
  the OpenSpec CLI
- **AND** the OpenSpec CLI runs on that runtime independently of the gateway's
  internal Node.

#### Scenario: Node installer integrity drift is detected

- **WHEN** the upstream Node installer script content differs from the pinned
  integrity hash recorded in the build
- **THEN** the integrity check fails and the build stops
- **SO THAT** an unverified installer is never executed in the image.

### Requirement: Claude crews add no Claude Code attribution
A crew image built with the claude agent toolchain SHALL configure Claude Code, at the managed (system-wide) settings level, to add no attribution to commits or pull requests. The setting SHALL live outside the crew's home volume, so it applies to every crew launched from the image whatever that volume already contains, and SHALL take precedence over user, project and session settings. Images built without the claude toolchain SHALL NOT contain this setting.

#### Scenario: Claude crew commit has no co-author trailer
- **WHEN** an agent in a claude-backend crew commits through Claude Code
- **THEN** the commit message contains no `Co-Authored-By` trailer naming Claude

#### Scenario: Claude crew PR text has no attribution
- **WHEN** an agent in a claude-backend crew writes a pull request description through Claude Code
- **THEN** the description contains no "Generated with Claude Code" text

#### Scenario: Existing home volume does not hide the setting
- **WHEN** a claude crew is launched from a rebuilt image onto a home volume created by an earlier image, or its `~/.claude/` is replaced by credential injection
- **THEN** attribution is still disabled

#### Scenario: Session settings cannot re-enable attribution
- **WHEN** a session's project or local Claude Code settings are written at spawn time
- **THEN** attribution remains disabled

#### Scenario: Image without the claude toolchain is unchanged
- **WHEN** the crew image is built without the claude toolchain
- **THEN** it contains no Claude Code managed settings file

#### Scenario: Git identity is unaffected
- **WHEN** `crew.git.author.name` and `crew.git.author.email` are set or unset
- **THEN** commit author and committer identity behave as before; only the attribution text changes

### Requirement: Shared agent assets record the commit they were built from

The crew image SHALL fetch shared agent assets at a configurable ref that MAY be a branch, a tag or a full commit SHA. By default it SHALL use the maintainer-controlled `main` branch. Every build SHALL record the commit it baked in inside the image, and the image label SHALL record the requested ref.

#### Scenario: Default build
- **WHEN** an operator builds the crew image without overriding the shared agent assets ref
- **THEN** the assets are fetched from `main`, the resolved commit SHA is recorded inside the image, and the image label records `main`

#### Scenario: Operator selects a tag or commit
- **WHEN** an operator sets the shared agent assets ref to a versioned tag or a full commit SHA
- **THEN** the build fetches exactly that ref and the recorded commit matches it

#### Scenario: Inventory classifies the ref
- **WHEN** the dependency check runs
- **THEN** it reports whether the shared agent assets ref is a commit or a branch or tag ref, without failing on a branch default

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
