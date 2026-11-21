# crew-governance Specification

## Purpose

Enforce unforgeable governance ceilings on crew agents by injecting signed
security policies at crew setup time. Ghostship acts as a KiroCrew operator —
it writes `security_policy.json` and `admission_policy.json` into each crew
container before the gateway starts enforcing them. Policies are HMAC-signed
with the crew's `admiral_secret` so that a tampered policy is detected at boot.
The default policy targets platform integrity: blocking control-plane escape
paths and messaging integrations, while leaving filesystem, sandbox, and network
access open. Operators who need tighter controls can supply comp-specific
policy templates.

## Requirements

### Requirement: Transport injects per-crew security policy at setup

After the gateway is ready and the Admiral secret is written, the transport SHALL inject `security_policy.json` at `~/.kiro/crew/security_policy.json` from templates under `academy/policies/` (available at `/policies/`).

#### Scenario: Policy injected for new crew with known comp
- **WHEN** `launch(crew_id, composition="kirocrew")` completes setup using the legacy alias
- **THEN** `~/.kiro/crew/security_policy.json` exists in the container with the `kirocrew` comp's policy content (or default if no specific template), and the `launch()` response includes `policy_version`

#### Scenario: Policy injection falls back to default for unknown comp
- **WHEN** `launch(crew_id, composition="custom-unknown")` completes setup using the legacy alias
- **THEN** the default policy template is used and injected successfully; no error is raised for a missing comp template

#### Scenario: Policy injection failure is logged but does not abort launch
- **WHEN** the policy file write inside the container fails (e.g. permissions)
- **THEN** the failure is logged as a warning and `launch()` continues; `policy_version` is omitted from the response

### Requirement: Security policy selection uses resolved crew composition

The resolved `comp` SHALL select the policy, falling back to `default`; the legacy `composition` argument SHALL remain an alias, with `comp` authoritative when both are supplied.

#### Scenario: Matching comp and composition select the same template
- **WHEN** `launch(crew_id, comp="kirocrew", composition="kirocrew")` completes setup
- **THEN** the `kirocrew` policy template is selected and injected

#### Scenario: Conflicting comp and composition select policy by comp
- **WHEN** `launch(crew_id, comp="kirocrew", composition="spec-ops")` is called
- **THEN** the `kirocrew` policy template is selected and a warning naming both values is logged
### Requirement: Security policy is signed by the Admiral using the 0.3.x governance API

The transport SHALL place the HMAC-SHA256 signature in `security_policy.json` as `identity.signature` with issuer `ghostship`; `admission_policy.json` SHALL require signatures and trust `policy_signing_key`. That key SHALL be distinct from `admiral_secret`, and the old flat trust-key list SHALL NOT be used.

#### Scenario: Admission policy written alongside security policy

- **WHEN** a crew's security policy is injected
- **THEN** `~/.kiro/crew/admission_policy.json` is written with `require_policy_signature: true`
  and `trust_keys` as a dict keyed by issuer using the crew's `policy_signing_key`; the
  signature lives inside `security_policy.json` as `identity.signature`

#### Scenario: policy_signing_key is distinct from admiral_secret

- **WHEN** a new crew is created
- **THEN** the transport generates two separate secrets: `admiral_secret` (used for Admiral
  command authentication, written only to `crews.json` and `.admiral_secret` inside the
  container) and `policy_signing_key` (used only for policy signing, written to
  `crews.json` and placed in `trust_keys`)
- **AND** `admission_policy.json` inside the container contains only `policy_signing_key`,
  never `admiral_secret`

#### Scenario: Policy tampering is detected at gateway boot

- **WHEN** `security_policy.json` is modified inside the container after injection (e.g. by
  a compromised tool) and the gateway reloads
- **THEN** the gateway detects the invalid `identity.signature` and refuses to continue —
  the agent cannot forge a valid policy without the `policy_signing_key`

#### Scenario: Signature is embedded in the policy document not in the admission policy

- **WHEN** the transport injects a security policy
- **THEN** `security_policy.json` contains `identity.issuer` and `identity.signature`;
  `admission_policy.json` contains `trust_keys` as a dict mapping the issuer to the
  `policy_signing_key`

#### Scenario: Policy injection failure does not abort launch

- **WHEN** the exec script writing `security_policy.json` or `admission_policy.json` fails
  inside the container
- **THEN** the failure is logged as a warning, `launch()` continues without `policy_version`
  in the response, and the crew boots ungoverned rather than failing to launch
### Requirement: Default policy blocks platform escape paths

The default policy SHALL deny control-plane escape and code-injection commands and SHALL deny external messaging integrations.

#### Scenario: Default policy blocks control-plane escape paths
- **WHEN** an agent executes a command matching `commands.deny`
  (e.g. `git push origin main`)
- **THEN** the gateway denies the command regardless of the agent's own
  `deniedCommands` config — the policy ceiling is unforgeable

#### Scenario: Default policy denial lists are specific
- **WHEN** the default policy is loaded
- **THEN** `commands.deny` includes `git push`, `git remote add`, `gh`, and pipe-to-shell curl/wget patterns, while `channels.deny` covers Slack, Discord, Telegram, Teams, Webex, WeCom, and WeChat

### Requirement: Default policy does not impose operator access restrictions

The default policy SHALL NOT restrict filesystem writes, sandbox level, or network egress; operators needing tighter controls SHALL supply a custom `comp` policy.

#### Scenario: Default policy does not restrict filesystem or network
- **WHEN** an agent writes to any path inside the container or makes an
  outbound network request
- **THEN** the default policy does not interfere — these are container-level
  concerns, not policy-level ones

#### Scenario: Operator adds tighter controls via custom comp
- **WHEN** `launch(crew_id, comp="kirocrew-strict")` is called and a
  `strict.json` policy template exists in `academy/policies/`
- **THEN** the strict policy (with sandbox floor, filesystem bounds, etc) is
  injected instead of the default
### Requirement: Comp-specific policy variants

The comp registry MAY declare a `security_policy` key naming a policy
template variant (e.g. `"research"`). Research comps SHALL receive
a policy with broader `filesystem.write` prefixes and relaxed command denials,
reflecting the different risk profile of read-heavy investigative work.

#### Scenario: Research comp uses its own policy variant
- **WHEN** `launch(crew_id, comp="kirocrew-research")` completes
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

`_patch_crew_config` SHALL write the five bounded numeric fields (`spawn_min_memory_gb`, `resource_pressure_gb`, `resource_critical_gb`, `subagent_timeout_secs`, `subagent_max_turns`) only within KiroCrew 0.5.0 limits; invalid values SHALL return 4xx instead of being clamped, and configured ranges SHALL be audited.

#### Scenario: Numeric field within bounds is accepted
- **WHEN** `_patch_crew_config` writes a numeric field whose value falls within
  KiroCrew 0.5.0's allowed range
- **THEN** the gateway accepts the config and the crew starts normally

#### Scenario: Out-of-bounds value surfaces a clear error
- **WHEN** `_patch_crew_config` attempts to write a numeric field value outside
  the gateway's enforced range
- **THEN** the gateway rejects the request with a 4xx response, and the
  transport logs the rejection before proceeding with crew teardown

### Requirement: Zero disables the minimum spawn memory gate

A value of `0` for `spawn_min_memory_gb` SHALL remain a valid disable sentinel.

#### Scenario: spawn_min_memory_gb=0 is not rejected
- **WHEN** `GA_SPAWN_MIN_MEMORY_GB` is set to `0` and the gateway enforces bounds
- **THEN** the gateway accepts `spawn_min_memory_gb: 0` as a valid disable
  sentinel and does not return a 4xx
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

KiroCrew 0.5.0 uses per-connection isolation for MCP servers ("misbehaving
servers get isolated per-connection"). Ghostship's `_copy_agents()` SHALL
continue to automatically set `poolable: false` on any server entry that
contains a `headers` field when writing into a crew's `~/.kiro/mcp.json`.
The `poolable` field SHALL remain honoured by 0.5.0; catalogue entries do not
need to declare it explicitly.

#### Scenario: HTTP server with headers gets poolable: false
- **WHEN** a catalogue entry contains a `headers` field
- **THEN** the entry written into the crew's `mcp.json` includes `"poolable": false`

#### Scenario: HTTP server without headers is written as-is
- **WHEN** a catalogue entry has no `headers` field
- **THEN** the entry is written into `mcp.json` without a `poolable` key added

#### Scenario: poolable field still honoured under 0.5.0 per-connection isolation
- **WHEN** a crew runs on KiroCrew 0.5.0 and `mcp.json` contains `"poolable": false`
- **THEN** the gateway respects the field and does not pool that server across
  connections, consistent with 0.4.0 behaviour

### Requirement: Containerfiles pin to kirocrew:0.6.0

All ghostship Containerfiles that reference the KiroCrew base image SHALL pin
to `kirocrew:0.6.0`.

#### Scenario: Containerfile updated to 0.4.0 pin
- **WHEN** a ghostship Containerfile is built after this change
- **THEN** it resolves `FROM ghcr.io/kirodotdev/kirocrew:0.6.0` as the base
  layer and the resulting image is compatible with the 0.5.0 governance API

#### Scenario: Old pin triggers build failure
- **WHEN** a Containerfile still references `kirocrew:0.4.x` or `kirocrew:latest`
  after this change is applied
- **THEN** the build CI job fails or the resulting image is flagged as
  incompatible during the regression test pass

### Requirement: Auth-disabled startup warning
When the transport starts without an API key configured, it MUST emit a WARNING-level log
entry clearly stating that all endpoints are publicly accessible. An INFO-level message is
not sufficient. The warning MUST appear before any request is served.

#### Scenario: Auth disabled at startup emits WARNING
- **WHEN** the transport starts with `GA_API_KEY` unset or empty
- **THEN** a WARNING-level log entry is emitted before the first request is handled
- **AND** the message states that all endpoints are publicly accessible

#### Scenario: Auth enabled at startup does not emit warning
- **WHEN** the transport starts with `GA_API_KEY` set to a non-empty value
- **THEN** no auth-disabled warning is emitted

### Requirement: Query string sanitisation
The transport MUST sanitise query strings before forwarding them to crew gateways. At minimum,
query strings containing CR, LF, or NUL characters MUST be rejected. Re-encoding via a
parse-then-encode round-trip is required to normalise encoding. A closed parameter allowlist
is the preferred long-term approach and SHOULD be added once all proxied parameters are
documented.

#### Scenario: CRLF in query string is rejected
- **WHEN** a request is proxied to a crew gateway with a query string containing CR or LF characters
- **THEN** the transport strips or rejects the offending characters before forwarding

#### Scenario: Clean query string passes through
- **WHEN** a request is proxied with a well-formed query string containing no control characters
- **THEN** the query string is forwarded to the crew gateway unchanged

### Requirement: policy_signing_key is persisted in the crew registry

The transport SHALL store `policy_signing_key` in the `crews.json` registry entry for each
crew, alongside `admiral_secret`. This allows the transport to re-inject the correct policy
on container restart without regenerating the key (which would invalidate the existing
`trust_keys` inside the container).

#### Scenario: policy_signing_key written to crews.json at crew creation

- **WHEN** `_finish_crew_setup()` completes successfully and writes the crew registry entry
- **THEN** the entry in `crews.json` includes a `policy_signing_key` field containing the
  hex-encoded key that was used to sign and inject the crew's policy

#### Scenario: policy_signing_key absent for pre-trn-53 crews

- **WHEN** a crew entry in `crews.json` predates this change and has no `policy_signing_key`
  field
- **THEN** the transport treats the field as absent and makes no attempt to re-inject or
  validate the policy for that crew during normal operation

### Requirement: policy_signing_key is rotated only at crew creation

The `policy_signing_key` SHALL be generated once per crew at creation time and reused for
the lifetime of the crew. It SHALL NOT be rotated on container restart. Rotation occurs
implicitly when a crew is destroyed and recreated.

#### Scenario: Container restart does not change trust_keys

- **WHEN** a crew container is stopped and restarted (e.g. idle-stop recovery via
  `_ensure_crew_running`)
- **THEN** the `policy_signing_key` in `crews.json` is unchanged, and the existing
  `admission_policy.json` inside the container (on the home volume) remains valid

### Requirement: Governance policy templates validated against 0.5.0 stricter validator

KiroCrew 0.5.0 hard-fails crew startup when `security_policy.json` contains a
misspelled `sandbox` key or a malformed `publish` section. Previously these were
silently ignored. The policy templates in `academy/policies/` SHALL be
confirmed well-formed against the 0.5.0 schema before the image pin is bumped.

#### Scenario: Well-formed policy template accepted by 0.5.0 gateway
- **WHEN** a crew starts with a security policy injected from a validated template
- **THEN** the 0.5.0 gateway accepts the policy without a validation error

#### Scenario: Misspelled sandbox key hard-fails in 0.5.0
- **WHEN** `security_policy.json` contains a key spelled `sandox` (or any
  unrecognised key in the `sandbox` section)
- **THEN** the 0.5.0 gateway rejects the policy and the crew fails to start,
  rather than ignoring the misspelling as 0.4.0 did

### Requirement: Claude crews suppress interactive approval prompts

For Claude backend launches, the transport SHALL suppress Claude Code's interactive approval prompts so headless sessions do not stall.

#### Scenario: Claude crew does not stall on tool approval prompts
- **WHEN** a crew is launched with `GA_CREW_ACP_BACKEND=claude` and an agent task calls a tool
- **THEN** the tool executes without waiting for interactive approval; no stall occurs in a headless container

### Requirement: Claude governance limits are documented

The spec and `docs/architecture.md` SHALL state that the command-deny policy still applies to Claude crews but KiroCrew's per-call approval gate does not.

#### Scenario: KiroCrew governance ceiling still enforced for Claude crews
- **WHEN** an agent running on the Claude backend attempts a command matching `commands.deny` in the crew's `security_policy.json`
- **THEN** the KiroCrew gateway rejects the command regardless of backend — the policy ceiling is enforced at the gateway level, not the ACP client level

#### Scenario: Governance gap documented in architecture docs
- **WHEN** an operator reads `docs/architecture.md`
- **THEN** they find a note explaining that Claude Code crews bypass KiroCrew's per-call tool approval gate but remain subject to the signed security policy ceiling
### Requirement: Codex sessions require verified read-only ACP mode

The ACP gate SHALL verify `mode=read-only` at `session/new` and apply it before the first prompt; otherwise it SHALL refuse the session.

#### Scenario: Codex session refused when not read-only
- **WHEN** a Codex-backend crew's `session/new` does not advertise `mode=read-only`
- **THEN** the ACP tool gate refuses the session before the first prompt rather than proceeding with an unverified mode

### Requirement: Codex crews retain the signed governance ceiling

The signed `commands.deny` policy SHALL remain enforced by the gateway regardless of backend.

#### Scenario: KiroCrew governance ceiling still enforced for Codex crews
- **WHEN** an agent running on the Codex backend attempts a command matching `commands.deny` in the crew's `security_policy.json`
- **THEN** the KiroCrew gateway rejects the command regardless of backend — the policy ceiling is enforced at the gateway level, not the ACP client level

### Requirement: Codex adapter credential homes are masked

The adapter's credential home (`~/.codex/auth.json`) and equivalent env-override roots SHALL be hidden from its child process to compensate for ACP-v1 read-visibility gaps.

#### Scenario: Codex adapter cannot reach other credential homes
- **WHEN** a Codex-backend crew session runs
- **THEN** the adapter's child process cannot read `~/.codex/auth.json` (its own token store) nor the standard-tier credential homes; those directories are masked at the OS boundary

### Requirement: Codex governance model is documented

The spec and `docs/architecture.md` SHALL describe the read-only ACP mode, signed policy ceiling, per-call approval bypass, and credential-home mask.

#### Scenario: Governance model documented in architecture docs
- **WHEN** an operator reads `docs/architecture.md`
- **THEN** they find a note explaining that Codex crews bypass ghostship's per-call approval gate, run under a verified read-only ACP mode, remain subject to the signed policy ceiling, and that the credential-dir OS mask compensates for the ACP-v1 read-visibility gap
### Requirement: SEL signing key is resolved from the KiroCrew trust root

Any future SEL consumer SHALL resolve the key under `$KIROCREW_HOME/trust/` and SHALL NOT hardcode legacy or bare relative paths. No current ghostship code reads the SEL key; it is distinct from `.local_secret`, `policy_signing_key`, and `admiral_secret`.

#### Scenario: Future SEL-reading code uses the trust root path
- **WHEN** any ghostship module is written or modified to read, verify, or reference the KiroCrew SEL signing key
- **THEN** it SHALL resolve the key under `$KIROCREW_HOME/trust/` and SHALL NOT contain a string literal matching `sel_key`, `sel-key`, `sel.key`, or `/sel/` as a path segment

#### Scenario: Grep of transport/ finds no pre-0.9.0 SEL path literal
- **WHEN** `grep -rnE '(sel_key|sel\.key|/sel/)' transport/` is run against the ghostship source tree
- **THEN** it returns no matches that resolve to a KiroCrew SEL key path; the only permitted hits are the known unrelated literals: the SQL `SELECT` keyword in `transport/container_scripts/read_auth.py` and the `.local_secret` docstring near `transport/lifecycle.py:321`

#### Scenario: Crew boots on KiroCrew 0.9.0 without SEL-related error
- **WHEN** a ghostship-managed crew is launched against a KiroCrew `0.9.0` (or later) gateway
- **THEN** the gateway log contains no SEL-related error attributable to a missing or incorrect ghostship SEL key reference; ghostship requires no code change for SEL signing to function
