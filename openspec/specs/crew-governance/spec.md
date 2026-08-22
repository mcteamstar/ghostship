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

### Requirement: Security policy is HMAC-signed by the Admiral

The transport SHALL compute an HMAC-SHA256 signature over the canonical
(JSON-sorted-keys) policy body using the crew's `admiral_secret`, then write
an `admission_policy.json` to `~/.kiro/crew/admission_policy.json` containing
`require_policy_signature: true` and the computed signature as a trust key.

#### Scenario: Admission policy written alongside security policy
- **WHEN** a crew's security policy is injected
- **THEN** `~/.kiro/crew/admission_policy.json` is also written with
  `require_policy_signature: true` and a trust key carrying the
  HMAC-SHA256 signature over the canonical policy body

#### Scenario: Policy tampering is detected at gateway boot
- **WHEN** `security_policy.json` is modified inside the container after
  injection (e.g. by a compromised tool) and the gateway reloads
- **THEN** the gateway detects the signature mismatch via the admission policy
  and refuses to continue — the agent cannot forge a valid policy without
  the `admiral_secret`

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
