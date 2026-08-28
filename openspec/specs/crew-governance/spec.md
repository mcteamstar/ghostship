# crew-governance Specification

## Purpose

Enforce unforgeable governance ceilings on crew agents by injecting signed
security policies at crew setup time. Ghostship acts as a KiroCrew operator —
it writes `security_policy.json` and `admission_policy.json` into each crew
container before the gateway starts enforcing them. Policies are HMAC-signed
with the crew's `admiral_secret` so that a tampered policy is detected at boot.
The default policy targets platform integrity: blocking control-plane escape
paths and messaging integrations, while leaving filesystem, sandbox, and network
access open. Operators who need tighter controls can supply composition-specific
policy templates.

## Requirements

### Requirement: Transport injects per-crew security policy at setup

The transport SHALL inject a `security_policy.json` into
`~/.kiro/crew/security_policy.json` inside each crew container during
`_finish_crew_setup`, after the gateway is ready and the `admiral_secret` has
been written. The policy SHALL be rendered from a template keyed by the
crew's composition name, falling back to the `default` template when no
composition-specific template exists.

Policy templates live in `academy/policies/` and are bind-mounted into the
transport container at `/policies/`.

#### Scenario: Policy injected for new crew with known composition
- **WHEN** `launch(crew_id, composition="kirocrew")` completes setup
- **THEN** `~/.kiro/crew/security_policy.json` exists in the container with
  the `kirocrew` composition's policy content (or default if no specific
  template), and the `launch()` response includes `policy_version`

#### Scenario: Policy injection falls back to default for unknown composition
- **WHEN** `launch(crew_id, composition="custom-unknown")` completes setup
- **THEN** the default policy template is used and injected successfully;
  no error is raised for a missing composition template

#### Scenario: Policy injection failure is logged but does not abort launch
- **WHEN** the policy file write inside the container fails (e.g. permissions)
- **THEN** the failure is logged as a warning and `launch()` continues;
  `policy_version` is omitted from the response

### Requirement: Security policy is signed by the Admiral using the 0.3.x governance API

The transport SHALL embed the HMAC-SHA256 signature as `identity.signature` inside `security_policy.json` (with `identity.issuer: "ghostship"`), and SHALL write `admission_policy.json` with `require_policy_signature: true` and `trust_keys: {"ghostship": <admiral_secret>}`. The old flat `trust_keys` list approach SHALL NOT be used.

#### Scenario: Admission policy written alongside security policy
- **WHEN** a crew's security policy is injected
- **THEN** `~/.kiro/crew/admission_policy.json` is written with `require_policy_signature: true` and `trust_keys` as a dict keyed by issuer; the signature lives inside `security_policy.json` as `identity.signature`

#### Scenario: Policy tampering is detected at gateway boot
- **WHEN** `security_policy.json` is modified inside the container after
  injection (e.g. by a compromised tool) and the gateway reloads
- **THEN** the gateway detects the invalid `identity.signature` and refuses to continue — the agent cannot forge a valid policy without the `admiral_secret`

#### Scenario: Signature is embedded in the policy document not in the admission policy
- **WHEN** the transport injects a security policy
- **THEN** `security_policy.json` contains `identity.issuer` and `identity.signature`; `admission_policy.json` contains `trust_keys` as a dict mapping the issuer to the HMAC secret

#### Scenario: Policy injection failure does not abort launch
- **WHEN** the exec script writing `security_policy.json` or `admission_policy.json` fails inside the container
- **THEN** the failure is logged as a warning, `launch()` continues without `policy_version` in the response, and the crew boots ungoverned rather than failing to launch

### Requirement: Default policy enforces platform integrity not access restriction

The default security policy (`academy/policies/default.json`) SHALL focus
exclusively on platform integrity — preventing agents from subverting the
control plane. The container is the security boundary; the default policy does
not restrict filesystem writes, sandbox level, or network egress.

The default policy SHALL deny:
- `commands.deny` patterns that escape the container or inject code:
  `git push`, `git remote add`, `gh`, pipe-to-shell curl/wget patterns
- `channels.deny` for all messaging integrations (Slack, Discord, Telegram,
  Teams, Webex, WeCom, WeChat) — agents should not connect to external
  messaging platforms independently

Operators who need tighter controls SHALL supply a custom composition policy
(e.g. `kirocrew-strict`) adding `sandbox.min_level`, `filesystem.write`
bounds, or additional `commands.deny` patterns.

#### Scenario: Default policy blocks control-plane escape paths
- **WHEN** an agent executes a command matching `commands.deny`
  (e.g. `git push origin main`)
- **THEN** the gateway denies the command regardless of the agent's own
  `deniedCommands` config — the policy ceiling is unforgeable

#### Scenario: Default policy does not restrict filesystem or network
- **WHEN** an agent writes to any path inside the container or makes an
  outbound network request
- **THEN** the default policy does not interfere — these are container-level
  concerns, not policy-level ones

#### Scenario: Operator adds tighter controls via custom composition
- **WHEN** `launch(crew_id, composition="kirocrew-strict")` is called and a
  `strict.json` policy template exists in `academy/policies/`
- **THEN** the strict policy (with sandbox floor, filesystem bounds, etc) is
  injected instead of the default

### Requirement: Composition-specific policy variants

The composition registry MAY declare a `security_policy` key naming a policy
template variant (e.g. `"research"`). Research-composition crews SHALL receive
a policy with broader `filesystem.write` prefixes and relaxed command denials,
reflecting the different risk profile of read-heavy investigative work.

#### Scenario: Research composition uses its own policy variant
- **WHEN** `launch(crew_id, composition="kirocrew-research")` completes
- **THEN** the research policy template is injected, not the default

### Requirement: crews and launch report policy version

Both `launch()` and the per-crew entries in `crews()` SHALL include a
`policy_version` field reflecting the policy version that was applied at
setup. Crews launched before this change have no `policy_version` field.

#### Scenario: Admiral can verify governance state from crews()
- **WHEN** the Admiral calls `crews()`
- **THEN** each crew entry includes `policy_version` (e.g. `"1"`) if it was
  launched with policy injection enabled, or omits the field for older crews

### Requirement: Numeric config fields are bounds-enforced in KiroCrew 0.4.0

The `_patch_crew_config` function SHALL only write numeric config fields that
fall within KiroCrew 0.4.0's enforced bounds. Any field value outside the
allowed range is now rejected with a 4xx response instead of being silently
clamped. The transport SHALL audit each numeric field it writes and ensure its
default and operator-settable range stays within the gateway-enforced bounds.

Fields that carry enforced bounds in 0.4.0 include `spawn_min_memory_gb`,
`resource_pressure_gb`, `resource_critical_gb`, `subagent_timeout_secs`, and
`subagent_max_turns`. A value of `0` for `spawn_min_memory_gb` SHALL remain
a valid disable sentinel and SHALL NOT be rejected by the gateway.

#### Scenario: Numeric field within bounds is accepted
- **WHEN** `_patch_crew_config` writes a numeric field whose value falls within
  KiroCrew 0.4.0's allowed range
- **THEN** the gateway accepts the config and the crew starts normally

#### Scenario: spawn_min_memory_gb=0 is not rejected
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is set to `0` and the gateway enforces bounds
- **THEN** the gateway accepts `spawn_min_memory_gb: 0` as a valid disable
  sentinel and does not return a 4xx

#### Scenario: Out-of-bounds value surfaces a clear error
- **WHEN** `_patch_crew_config` attempts to write a numeric field value outside
  the gateway's enforced range
- **THEN** the gateway rejects the request with a 4xx response, and the
  transport logs the rejection before proceeding with crew teardown

### Requirement: Config fields with unexpanded shell variable references are rejected

KiroCrew 0.4.0 rejects any config field value that contains a literal `$`
followed by alphanumeric characters or `{…}` (an unexpanded shell variable
reference). The transport SHALL ensure all config field values written to
`config.local.json` are fully expanded before writing — no field value SHALL
contain a literal `$VAR` or `${VAR}` string.

#### Scenario: Fully expanded config value is accepted
- **WHEN** `_patch_crew_config` writes a config field whose value is a fully
  resolved Python string (no literal `$` variable references)
- **THEN** the gateway accepts the field without error

#### Scenario: Unexpanded variable reference is rejected
- **WHEN** a config field value contains a literal string such as `"$HOME"`
  or `"${KIROCREW_DIR}/config"`
- **THEN** the gateway rejects the config with a 4xx response indicating an
  unexpanded variable reference

### Requirement: Env-declaring MCP servers are not pooled by default

KiroCrew 0.4.0 changes the default pooling behaviour: any MCP server spec that
declares an `env` block is now pooled across agents by default, which breaks
stateful servers. Any MCP server spec inside ghostship that declares an `env`
block and whose state is per-agent or per-session SHALL include `"poolable": false`
to opt out of the new default.

#### Scenario: Stateful env-declaring server carries poolable=false
- **WHEN** an MCP server spec in the ghostship crew configuration declares an
  `env` block and manages per-session state
- **THEN** the spec includes `"poolable": false` so KiroCrew 0.4.0 does not
  pool it across agents

#### Scenario: Stateless env-declaring server may omit poolable
- **WHEN** an MCP server spec declares an `env` block and its state is fully
  shared or idempotent across sessions
- **THEN** the absence of `"poolable": false` is intentional and the server
  may be pooled

#### Scenario: MCP server without env block is unaffected
- **WHEN** an MCP server spec declares no `env` block
- **THEN** KiroCrew 0.4.0's new pooling default does not apply to it and no
  change is required

### Requirement: Containerfiles pin to kirocrew:0.4.0

All ghostship Containerfiles that reference the KiroCrew base image SHALL pin
to `kirocrew:0.4.0`. A Containerfile left pinned at `0.3.x` or `latest` will
pull an incompatible base image that does not carry the 0.4.0 API fixes.

#### Scenario: Containerfile updated to 0.4.0 pin
- **WHEN** a ghostship Containerfile is built after this change
- **THEN** it resolves `FROM ghcr.io/kirodotdev/kirocrew:0.4.0` as the base
  layer and the resulting image is compatible with the 0.4.0 API surface

#### Scenario: Old pin triggers build failure
- **WHEN** a Containerfile still references `kirocrew:0.3.x` or `kirocrew:latest`
  after this change is applied
- **THEN** the build CI job fails or the resulting image is flagged as
  incompatible during the regression test pass
