## Purpose

Defines how the OpenCode agent backend is installed, configured, and enabled in Ghostship spec-ops crews, following the same toolchain pattern as the Claude and Codex backends.

## ADDED Requirements

### Requirement: OpenCode toolchain installs the opencode binary

When `opencode` is listed in `GA_AGENT_BACKENDS`, the spec-ops crew image build SHALL install the `opencode-ai` npm package into the crew image by running `opencode.sh` from the toolchains directory. The installed binary SHALL be the version pinned in `opencode.sh`. The install command is `npm install -g opencode-ai`.

#### Scenario: opencode binary present when backend is enabled
- **WHEN** `GA_AGENT_BACKENDS` includes `opencode` and a spec-ops crew image is built
- **THEN** the `opencode` binary is present in the built image at the standard npm global bin location

#### Scenario: opencode binary absent when backend is not enabled
- **WHEN** `GA_AGENT_BACKENDS` does not include `opencode` and a spec-ops crew image is built
- **THEN** no `opencode-ai` package is installed in the image

### Requirement: OpenCode authenticates via a stored credential file

OpenCode reads its provider credentials from `~/.local/share/opencode/auth.json` on the host. Ghostship SHALL provide a login container mechanism so an operator can run `opencode auth login` inside an ephemeral container, capture the resulting auth file, and store it as a crew secret (analogous to `ga-claude-auth`). At crew launch, the stored `ga-opencode-auth` credential SHALL be mounted into the crew container's auth location so OpenCode sessions can authenticate without an interactive sign-in.

#### Scenario: Login container produces an auth credential
- **WHEN** the operator runs the opencode login flow in the ghostship login container
- **THEN** the resulting `~/.local/share/opencode/auth.json` is captured and stored as `ga-opencode-auth`

#### Scenario: Credential injected at crew launch
- **WHEN** `ga-opencode-auth` exists and a crew is launched with opencode enabled
- **THEN** the credential is available to opencode inside the crew container at the expected location

#### Scenario: Session refused when no credential exists
- **WHEN** no `ga-opencode-auth` credential is stored and an OpenCode session is requested
- **THEN** the transport returns an error indicating the operator must run the opencode login flow, and no session is started

### Requirement: OpenCode backend is a Preview feature requiring explicit opt-in

The OpenCode backend SHALL be treated as a Preview feature. It SHALL NOT be the default backend unless explicitly set via `GA_CREW_ACP_BACKEND=opencode`. Documentation SHALL note that OpenCode is upstream-preview status in KiroCrew and may have capability gaps compared to the kiro-cli backend.

#### Scenario: Default backend is kiro when opencode is enabled but default is not set
- **WHEN** `GA_AGENT_BACKENDS=opencode` and `GA_CREW_ACP_BACKEND` is unset
- **THEN** new crews default to the kiro backend, not opencode

#### Scenario: OpenCode is the default when explicitly set
- **WHEN** `GA_AGENT_BACKENDS=opencode` and `GA_CREW_ACP_BACKEND=opencode`
- **THEN** new crews launch on the OpenCode backend
