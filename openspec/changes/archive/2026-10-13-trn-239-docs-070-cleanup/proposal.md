# Proposal

**Plane ticket:** TRN-239

## Why

The 0.7.0 independent review (indy-070) flagged three doc accuracy issues: the agents.md tool-set table incorrectly describes what Wraith and Reaper can do; architecture.md and auth.md still reference deprecated env var names from TRN-213; and the configuration.md "Extending the crew image" Dockerfile example is broken — it extends the wrong base image and claims Node.js is already included when it isn't. These are pure documentation fixes with no code or behaviour changes.

## What Changes

- **agents.md** — Correct the tool-set table: Wraith lacks `write` and `code`; Reaper lacks `code`. The current claim "all five workers share the same tool set" is factually wrong for both.
- **architecture.md** — Replace references to deprecated `GA_CREW_ACP_BACKEND` and `GA_AGENT_BACKENDS` with the canonical `GA_CREW_AGENT` (introduced in TRN-213). A single parenthetical note that the old names are still accepted with a warning is sufficient.
- **auth.md** — Same deprecated-var replacement as architecture.md (lines 162, 300).
- **configuration.md** — Replace the broken "Extending the crew image" Dockerfile example. The current example extends `ghcr.io/kirodotdev/kirocrew@sha256:…` directly, bypassing all ghostship layers (mail stack, scripts, Node.js, openspec CLI). The correct extension point is `localhost/spec-ops-mid:latest`. The `# already included` comment for nodejs is also wrong and should be removed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a pure documentation accuracy fix — no spec-level behaviour changes. `skip_specs: true` is set in `.openspec.yaml`.

## Impact

- `docs/agents.md` — tool-set table update
- `docs/architecture.md` — deprecated env var references
- `docs/auth.md` — deprecated env var references
- `docs/configuration.md` — Dockerfile example replacement
