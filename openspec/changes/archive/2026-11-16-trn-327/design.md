# Design

## Context

The installer currently maps `backends.default` directly to the comma-separated
`GA_CREW_AGENT` environment variable. Runtime parsing treats that value as both an
ordered enabled-backend list and a default selector, then appends Kiro implicitly.
Backend-specific YAML sections are currently flattened for settings but do not
participate in enablement. See `proposal.md` and the spec deltas for the desired
contract.

## Goals / Non-Goals

**Goals:**

- Represent the implicit backend with one scalar value.
- Derive the enabled/bundled backend set from the resolved `backends.<name>` sections.
- Keep backend selection, toolchain build arguments, login availability, launch validation, and inert-setting warnings consistent.
- Give operators an actionable migration path from the old list form.

**Non-Goals:**

- Changing per-backend model precedence or model identifiers.
- Adding backend failover/retry behavior.
- Changing per-crew explicit `launch(backend=...)` semantics beyond enablement validation.
- Automatically rewriting existing operator-owned YAML files.

## Decisions

### Use raw optional-backend-section presence for enablement

The config resolver must retain enough information to distinguish an absent optional
backend section from a section populated only by built-in defaults. Kiro is a special
built-in backend and is always enabled. Claude and Codex enablement should be computed
from operator/XDG configuration layers, then emitted as the existing runtime backend
list needed by the container. This avoids treating every schema field in the built-in
defaults tree as an enabled optional toolchain.

An explicitly present empty mapping (`backends.claude: {}` or `backends.codex: {}`)
is an opt-in declaration and inherits the backend's built-in model/runtime defaults.
A missing section remains disabled.

Alternative considered: keep a separate `backends.enabled` list. Rejected because it
duplicates backend names and reintroduces two sources of truth.

### Keep the runtime environment as a derived compatibility boundary

`GA_CREW_AGENT` may remain a comma-separated internal environment value for the
transport and compose/build layers, but it will be generated from the enabled backend
sections. A separate scalar environment value or a reordered list is not needed once
the first-entry convention is removed from configuration parsing.

### Validate the scalar default against enabled backends during install

Install-time validation should fail before image builds when the scalar default is
unknown or an optional backend section is absent. If omitted, the scalar default is
`kiro`. Runtime startup should retain equivalent defense for hand-authored environments
and direct container use.

### Migrate legacy list configuration explicitly

The old list form cannot be interpreted losslessly when backend sections are the
source of truth. The installer should reject it with a message explaining that the
first entry becomes `backends.default` and each intended backend needs a corresponding
`backends.<name>` section. Existing configs are not edited automatically.

## Risks / Trade-offs

- **[Existing configs use list enablement]** → Provide a precise migration error and
  update the example/docs; add tests for both valid scalar and rejected list forms.
- **[Built-in defaults accidentally enable optional backends]** → Track configured
  Claude/Codex section presence separately from the merged defaults tree while always
  including Kiro, and test minimal configs.
- **[YAML null is confused with an empty mapping]** → Document `{}` as the canonical
  opt-in form and normalize/validate bare null consistently rather than silently
  producing a partially enabled backend.
- **[Direct `GA_CREW_AGENT` users bypass YAML semantics]** → Preserve runtime parsing
  for the derived comma-separated value, retain implicit Kiro, and validate the
  scalar default against the derived enabled set.
- **[Toolchain/build and runtime sets diverge]** → Generate both from one normalized
  enabled-backend result and add integration assertions for image/toolchain arguments.
- **[Model IDs use different backend spellings]** → Keep shipped personas unpinned and
  configure backend defaults with Kiro's dotted spelling, Claude's native hyphenated
  spelling, and Codex's `gpt-6-luna` identifier; verify all three live paths.

## Migration Plan

1. Update `config/ghostship.yaml.example`, docs, and schema deltas to use a scalar
   default plus backend sections.
2. Update the resolver and installer to normalize the new shape and derive the enabled
   set; reject legacy lists with migration guidance.
3. Update runtime backend parsing and launch/login validation to retain implicit Kiro,
   default the scalar selector to Kiro, and derive optional backends from sections.
4. Run unit/integration tests, then run `ghostship install` with the migrated local
   config to rebuild the intended toolchains.
5. Existing crews retain their recorded backend; only newly launched or explicitly
   recreated crews use the new installed toolchain set.

Rollback consists of restoring the previous installer/runtime version and using the
old list-form configuration during the compatibility window.
